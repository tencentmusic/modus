import com.sun.source.tree.ClassTree;
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.MethodInvocationTree;
import com.sun.source.tree.MethodTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.SourcePositions;
import com.sun.source.util.TreePath;
import com.sun.source.util.TreePathScanner;
import com.sun.source.util.Trees;

import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.ExecutableElement;
import javax.lang.model.element.Modifier;
import javax.lang.model.element.TypeElement;
import javax.lang.model.element.VariableElement;
import javax.lang.model.type.DeclaredType;
import javax.lang.model.type.TypeMirror;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
import java.io.File;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Deque;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Compiler-front-end JSONL provider used by Modus. No project code is executed. */
public final class ModusJavaAnalyzer {
    // Root and build identity are fixed for one invocation. Scanner state below
    // follows the current compilation unit and nested declaration only.
    private final Path root;
    private final String buildUnit;
    private final String contextDigest;
    private final Trees trees;
    private final SourcePositions positions;
    private final Set<String> emittedNodes = new HashSet<String>();
    private CompilationUnitTree unit;
    private String currentType = "";
    private final Deque<String> callers = new ArrayDeque<String>();

    private ModusJavaAnalyzer(Path root, String buildUnit, String contextDigest, Trees trees) {
        this.root = root.toAbsolutePath().normalize();
        this.buildUnit = buildUnit;
        this.contextDigest = contextDigest;
        this.trees = trees;
        this.positions = trees.getSourcePositions();
    }

    /**
     * Encode a JSON string body without changing the provider's wire format.
     * Control characters must be escaped even when they came from annotations.
     */
    private static String esc(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            switch (c) {
                case '\\':
                    out.append("\\\\");
                    break;
                case '"':
                    out.append("\\\"");
                    break;
                case '\n':
                    out.append("\\n");
                    break;
                case '\r':
                    out.append("\\r");
                    break;
                case '\t':
                    out.append("\\t");
                    break;
                default:
                    if (c < 32) {
                        out.append(String.format("\\u%04x", (int)c));
                    } else {
                        out.append(c);
                    }
            }
        }
        return out.toString();
    }

    /**
     * Derive the existing compact edge identity from its ordered components.
     * The fallback remains for compatibility with restricted Java runtimes.
     */
    private static String sha(String value) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] bytes = digest.digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder out = new StringBuilder();
            for (byte item : bytes) {
                out.append(String.format("%02x", item));
            }
            return out.substring(0, 24);
        } catch (Exception ignored) {
            return Integer.toHexString(value.hashCode());
        }
    }

    // Paths are repository-relative when javac exposes a filesystem URI. Foreign
    // source objects retain their own names so diagnostics still have an anchor.
    private String rel(CompilationUnitTree value) {
        try {
            Path file = Paths.get(value.getSourceFile().toUri()).toAbsolutePath().normalize();
            return root.relativize(file).toString().replace(File.separatorChar, '/');
        } catch (Exception exc) {
            return value.getSourceFile().getName().replace('\\', '/');
        }
    }

    // javac uses negative positions for synthetic trees; keep the historical
    // first-line fallback rather than inventing a precise source location.
    private long line(CompilationUnitTree sourceUnit, Tree tree) {
        long offset = positions.getStartPosition(sourceUnit, tree);
        return offset < 0 ? 1 : sourceUnit.getLineMap().getLineNumber(offset);
    }

    private long line(Tree tree) {
        return line(unit, tree);
    }

    // Java source positions count UTF-16 code units. Consumers use the explicit
    // encoding field to distinguish these columns from Go's byte offsets.
    private long column(CompilationUnitTree sourceUnit, Tree tree) {
        long offset = positions.getStartPosition(sourceUnit, tree);
        return offset < 0 ? 1 : offset - sourceUnit.getLineMap().getStartPosition(
                sourceUnit.getLineMap().getLineNumber(offset)) + 1;
    }

    private long column(Tree tree) {
        return column(unit, tree);
    }

    // End offsets are exclusive, matching javac's SourcePositions contract.
    // Synthetic or missing ends collapse to the known start without extrapolation.
    private String rangeFields(CompilationUnitTree sourceUnit, Tree tree) {
        long start = positions.getStartPosition(sourceUnit, tree);
        long end = positions.getEndPosition(sourceUnit, tree);
        if (end < start || end < 0) {
            end = Math.max(0, start);
        }
        long endLine = sourceUnit.getLineMap().getLineNumber(end);
        long endColumn = end - sourceUnit.getLineMap().getStartPosition(endLine) + 1;
        return ",\"endLine\":" + endLine + ",\"endColumn\":" + endColumn
                + ",\"columnEncoding\":\"utf16\"";
    }

    // Preserve javac's annotation spelling as evidence; annotation interpretation
    // belongs to downstream framework adapters rather than this serializer.
    private static String annotations(Element element) {
        StringBuilder out = new StringBuilder("[");
        boolean first = true;
        for (AnnotationMirror annotation : element.getAnnotationMirrors()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append('"').append(esc(annotation.toString())).append('"');
        }
        return out.append(']').toString();
    }

    private static String typeName(TypeMirror mirror) {
        // Declared owners use a qualified type identity independent of generic
        // arguments. Other mirrors keep javac's spelling for compatibility.
        if (mirror instanceof DeclaredType) {
            Element element = ((DeclaredType)mirror).asElement();
            if (element instanceof TypeElement) {
                return ((TypeElement)element).getQualifiedName().toString();
            }
        }
        return mirror.toString();
    }

    // Owner and parameter types distinguish overloads independently of display
    // labels. Changing this spelling would change node and edge identities.
    private static String executableName(ExecutableElement element) {
        Element owner = element.getEnclosingElement();
        String ownerName = owner instanceof TypeElement
                ? ((TypeElement)owner).getQualifiedName().toString() : owner.toString();
        StringBuilder out = new StringBuilder(ownerName).append('#').append(element.getSimpleName()).append('(');
        boolean first = true;
        for (VariableElement parameter : element.getParameters()) {
            if (!first) {
                out.append(',');
            }
            first = false;
            out.append(parameter.asType().toString());
        }
        return out.append(')').toString();
    }

    // Every record carries the build context that produced the compiler binding.
    private String provenance() {
        return "{\"provider\":\"java-javac\",\"providerVersion\":\"1\",\"contextDigest\":\""
                + esc(contextDigest) + "\"}";
    }

    // Diagnostics share stdout's JSONL stream; javac's own messages use stderr.
    private void emitDiagnostic(String code, String message, String subject) {
        System.out.println("{\"recordKind\":\"diagnostic\",\"code\":\"" + esc(code)
                + "\",\"message\":\"" + esc(message)
                + "\",\"severity\":\"warning\",\"provider\":\"java-javac\""
                + ",\"buildUnitId\":\"" + esc(buildUnit) + "\",\"subject\":\""
                + esc(subject) + "\"}");
    }

    // Admit a stable identity once. Referenced external declarations may lack a
    // source tree, so an empty anchor set is meaningful rather than an error.
    private void emitNode(String id, String kind, String qualified, Tree tree, Element element, String owner) {
        if (id == null || id.isEmpty() || qualified == null || qualified.isEmpty()
                || buildUnit == null || buildUnit.isEmpty()) {
            emitDiagnostic(
                    "provider.java.empty-qualified-name",
                    "Skipped an anonymous or local declaration without a stable qualified name.",
                    unit == null ? "" : rel(unit));
            return;
        }
        if (!emittedNodes.add(id)) {
            return;
        }
        Tree anchorTree = tree;
        CompilationUnitTree anchorUnit = unit;
        if (anchorTree == null && element != null) {
            TreePath declaration = trees.getPath(element);
            if (declaration != null) {
                anchorTree = declaration.getLeaf();
                anchorUnit = declaration.getCompilationUnit();
            }
        }
        String anchors = anchorTree == null || anchorUnit == null ? "[]"
                : "[{\"file\":\"" + esc(rel(anchorUnit)) + "\",\"line\":"
                + line(anchorUnit, anchorTree) + ",\"column\":"
                + column(anchorUnit, anchorTree) + rangeFields(anchorUnit, anchorTree) + "}]";
        String attrs = "{\"annotations\":" + annotations(element)
                + (owner.isEmpty() ? "" : ",\"owner\":\"" + esc(owner) + "\"") + "}";
        System.out.println("{\"recordKind\":\"node\",\"id\":\"" + esc(id)
                + "\",\"kind\":\"" + kind + "\",\"language\":\"java\",\"qualifiedName\":\""
                + esc(qualified) + "\",\"buildUnitId\":\"" + esc(buildUnit)
                + "\",\"sourceAnchors\":" + anchors + ",\"attributes\":" + attrs
                + ",\"provenance\":" + provenance() + "}");
    }

    // Materialize declaration endpoints before an edge references them. This
    // avoids requiring consumers to synthesize nodes from unresolved edge text.
    private void ensureExternalNode(Element element) {
        if (element instanceof ExecutableElement) {
            ExecutableElement executable = (ExecutableElement)element;
            String qualified = executableName(executable);
            emitNode("java:" + qualified, "method", qualified, null, executable,
                    typeName(executable.getEnclosingElement().asType()));
        } else if (element instanceof TypeElement) {
            String qualified = ((TypeElement)element).getQualifiedName().toString();
            emitNode("java:" + qualified, "type", qualified, null, element, "");
        }
    }

    // 完整区间区分同起点的链式调用；合成调用保留位置缺失和操作种类。
    private void emitEdge(String from, String to, String relation, String operation,
                          String dispatch, String resolution, Tree tree, String evidence) {
        if (!emittedNodes.contains(from) || !emittedNodes.contains(to)) {
            emitDiagnostic(
                    "provider.java.dangling-edge-skipped",
                    "Skipped an edge whose declaration has no stable semantic node.",
                    unit == null ? "" : rel(unit));
            return;
        }
        boolean explicitSource = positions.getStartPosition(unit, tree) >= 0
                && positions.getEndPosition(unit, tree) > positions.getStartPosition(unit, tree);
        String callSite = explicitSource ? "{\"file\":\"" + esc(rel(unit))
                + "\",\"line\":" + line(tree) + ",\"column\":" + column(tree)
                + rangeFields(unit, tree) + "}" : "null";
        String identity = from + "\u001f" + to + "\u001f" + relation + "\u001f" + rel(unit)
                + "\u001f" + positions.getStartPosition(unit, tree)
                + "\u001f" + positions.getEndPosition(unit, tree)
                + "\u001f" + tree.getKind() + "\u001f" + operation + "\u001f" + dispatch;
        System.out.println("{\"recordKind\":\"edge\",\"id\":\"java-edge:" + sha(identity)
                + "\",\"from\":\"" + esc(from) + "\",\"to\":\"" + esc(to)
                + "\",\"relation\":\"" + relation + "\",\"resolution\":\"" + resolution
                + "\",\"operation\":\"" + esc(operation) + "\",\"dispatch\":\""
                + esc(dispatch) + "\",\"contractKey\":\"\",\"callSite\":" + callSite
                + ",\"evidence\":[\"" + esc(evidence) + "\"],\"attributes\":{\"syntheticSource\":"
                + (!explicitSource) + "},\"provenance\":"
                + provenance() + "}");
    }

    // The visitor records compiler observations only. A resolved interface call
    // remains interface dispatch; the provider does not guess its runtime target.
    private final class Scanner extends TreePathScanner<Void, Void> {
        @Override
        public Void visitCompilationUnit(CompilationUnitTree tree, Void unused) {
            unit = tree;
            return super.visitCompilationUnit(tree, unused);
        }

        @Override
        public Void visitClass(ClassTree tree, Void unused) {
            Element element = trees.getElement(getCurrentPath());
            // A nested class must restore its enclosing owner after traversal.
            String previous = currentType;
            if (element instanceof TypeElement) {
                TypeElement type = (TypeElement)element;
                currentType = type.getQualifiedName().toString();
                emitNode("java:" + currentType, "type", currentType, tree, type, "");
                for (TypeMirror parent : type.getInterfaces()) {
                    Element target = parent instanceof DeclaredType ? ((DeclaredType)parent).asElement() : null;
                    if (target instanceof TypeElement) {
                        ensureExternalNode(target);
                        String targetName = ((TypeElement)target).getQualifiedName().toString();
                        emitEdge("java:" + currentType, "java:" + targetName, "implements", "",
                                "static", "exact", tree, "javac type binding");
                    }
                }
            }
            Void result = super.visitClass(tree, unused);
            currentType = previous;
            return result;
        }

        @Override
        public Void visitMethod(MethodTree tree, Void unused) {
            Element element = trees.getElement(getCurrentPath());
            if (!(element instanceof ExecutableElement)) {
                return super.visitMethod(tree, unused);
            }
            ExecutableElement executable = (ExecutableElement)element;
            String qualified = executableName(executable);
            String id = "java:" + qualified;
            emitNode(id, "method", qualified, tree, executable, currentType);
            // Nested declarations need a stack, not one process-global caller.
            callers.push(id);
            Void result = super.visitMethod(tree, unused);
            callers.pop();
            return result;
        }

        @Override
        public Void visitVariable(VariableTree tree, Void unused) {
            Element element = trees.getElement(getCurrentPath());
            if (element instanceof VariableElement && !currentType.isEmpty()) {
                VariableElement variable = (VariableElement)element;
                String anns = annotations(variable);
                if (anns.contains("Reference") || anns.contains("Autowired") || anns.contains("Inject")
                        || anns.contains("Resource")) {
                    TypeMirror mirror = variable.asType();
                    Element target = mirror instanceof DeclaredType ? ((DeclaredType)mirror).asElement() : null;
                    if (target instanceof TypeElement) {
                        ensureExternalNode(target);
                        String targetName = ((TypeElement)target).getQualifiedName().toString();
                        emitEdge("java:" + currentType, "java:" + targetName, "injects",
                                variable.getSimpleName().toString(), "static", "exact", tree, anns);
                    }
                }
            }
            return super.visitVariable(tree, unused);
        }

        @Override
        public Void visitMethodInvocation(MethodInvocationTree tree, Void unused) {
            if (callers.isEmpty()) {
                return super.visitMethodInvocation(tree, unused);
            }
            Element element = trees.getElement(getCurrentPath());
            if (element instanceof ExecutableElement) {
                ExecutableElement executable = (ExecutableElement)element;
                ensureExternalNode(executable);
                String target = "java:" + executableName(executable);
                Element owner = executable.getEnclosingElement();
                String dispatch;
                if (executable.getModifiers().contains(Modifier.STATIC)) {
                    dispatch = "static";
                } else if (owner.getKind() == ElementKind.INTERFACE) {
                    dispatch = "interface";
                } else {
                    dispatch = "virtual";
                }
                emitEdge(callers.peek(), target, "calls", executable.getSimpleName().toString(),
                        dispatch, "exact", tree, "javac Trees.getElement");
            }
            return super.visitMethodInvocation(tree, unused);
        }
    }

    /**
     * Parse and bind the supplied source list, then emit declaration/call JSONL.
     * Annotation processing is disabled unless the caller explicitly enables it.
     *
     * @param args root, build unit, context digest, source-list file, classpath,
     *             and an optional annotation-processing flag
     * @throws Exception when source input or compiler setup cannot complete
     */
    public static void main(String[] args) throws Exception {
        if (args.length < 5) {
            System.err.println("usage: ModusJavaAnalyzer ROOT BUILD_UNIT CONTEXT_DIGEST "
                    + "SOURCES_FILE CLASSPATH [PROCESSORS]");
            System.exit(2);
        }
        Path root = Paths.get(args[0]);
        List<String> sourceNames = Files.readAllLines(Paths.get(args[3]), StandardCharsets.UTF_8);
        List<File> sourceFiles = new ArrayList<File>();
        for (String name : sourceNames) {
            if (!name.trim().isEmpty()) {
                sourceFiles.add(new File(name));
            }
        }
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("system Java compiler is unavailable");
        }
        StandardJavaFileManager manager = compiler.getStandardFileManager(null, null, StandardCharsets.UTF_8);
        Iterable<? extends JavaFileObject> objects = manager.getJavaFileObjectsFromFiles(sourceFiles);
        // Binding is sufficient for evidence. No class generation or project
        // application entry point is invoked by this provider.
        List<String> options = new ArrayList<String>(Arrays.asList("-Xlint:none", "-sourcepath", root.toString()));
        if (!"true".equals(args.length > 5 ? args[5] : "false")) {
            // The Python caller owns the explicit annotation-processor policy.
            options.add("-proc:none");
        }
        if (!args[4].isEmpty()) {
            options.add("-classpath");
            options.add(args[4]);
        }
        JavacTask task = (JavacTask)compiler.getTask(
                new PrintWriter(System.err), manager, null, options, null, objects);
        Iterable<? extends CompilationUnitTree> units = task.parse();
        // Analyze before traversing: Trees.getElement requires attributed trees.
        task.analyze();
        ModusJavaAnalyzer analyzer = new ModusJavaAnalyzer(root, args[1], args[2], Trees.instance(task));
        Scanner scanner = analyzer.new Scanner();
        for (CompilationUnitTree unit : units) {
            scanner.scan(unit, null);
        }
        manager.close();
    }
}
