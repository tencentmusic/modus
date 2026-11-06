// Command modus-go-analyzer emits compiler-bound Go declaration/call facts as JSONL.
// It intentionally uses only the official Go parser/type-checker SDK so Modus
// never downloads dependencies while analysing a repository.
package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/importer"
	"go/parser"
	"go/token"
	"go/types"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// sourceAnchor is shared by declarations and calls. Omitted end coordinates
// denote point observations, while calls carry their complete expression range.
type sourceAnchor struct {
	File           string `json:"file"`
	Line           int    `json:"line"`
	Column         int    `json:"column"`
	EndLine        int    `json:"endLine,omitempty"`
	EndColumn      int    `json:"endColumn,omitempty"`
	ColumnEncoding string `json:"columnEncoding"`
}

type provenance struct {
	Provider        string `json:"provider"`
	ProviderVersion string `json:"providerVersion"`
	ContextDigest   string `json:"contextDigest"`
}

// packageUnit owns the mutable type-checking state for one import path. The
// checking flag detects recursion before a completed package can be memoized.
type packageUnit struct {
	dir        string
	importPath string
	project    bool
	files      []*ast.File
	info       *types.Info
	pkg        *types.Package
	checking   bool
}

type packageRequest struct {
	ImportPath string   `json:"importPath"`
	Directory  string   `json:"directory"`
	Files      []string `json:"files"`
	Project    bool     `json:"project"`
}

type projectImporter struct {
	units    map[string]*packageUnit
	fallback types.Importer
	fset     *token.FileSet
}

func (p *projectImporter) Import(path string) (*types.Package, error) {
	// Request-local packages take precedence over the SDK importer's cache.
	// Neither path starts a module download or executes project initialization.
	if unit := p.units[path]; unit != nil {
		return p.check(unit)
	}
	return p.fallback.Import(path)
}

func (p *projectImporter) check(unit *packageUnit) (*types.Package, error) {
	if unit.pkg != nil {
		return unit.pkg, nil
	}
	if unit.checking {
		return nil, fmt.Errorf("Go import cycle involving %s", unit.importPath)
	}
	unit.checking = true
	defer func() { unit.checking = false }()
	unit.info = &types.Info{
		Types:      make(map[ast.Expr]types.TypeAndValue),
		Defs:       make(map[*ast.Ident]types.Object),
		Uses:       make(map[*ast.Ident]types.Object),
		Selections: make(map[*ast.SelectorExpr]*types.Selection),
	}
	conf := &types.Config{Importer: p, Error: func(error) {}}
	pkg, err := conf.Check(unit.importPath, p.fset, unit.files, unit.info)
	unit.pkg = pkg
	if pkg == nil {
		pkg = types.NewPackage(unit.importPath, filepath.Base(unit.dir))
		unit.pkg = pkg
		return pkg, err
	}
	// go list -e may retain packages with recoverable dependency errors. A
	// partially type-checked package still provides more useful object identity
	// than treating every selector in its importers as an unresolved name.
	return pkg, nil
}

func emit(value interface{}) {
	// One JSON object per line allows the Python caller to consume facts without
	// coupling its decoder to compiler progress or human-readable diagnostics.
	data, err := json.Marshal(value)
	if err == nil {
		fmt.Println(string(data))
	}
}

func stable(prefix string, parts ...string) string {
	// Preserve the separator and truncation width: both are persisted identity
	// contracts, not presentation choices for the current invocation.
	sum := sha256.Sum256([]byte(strings.Join(parts, "\x1f")))
	return prefix + ":" + hex.EncodeToString(sum[:])[:24]
}

func relative(root, path string) string {
	value, err := filepath.Rel(root, path)
	if err != nil {
		return filepath.ToSlash(path)
	}
	return filepath.ToSlash(value)
}

func anchorFor(root string, fset *token.FileSet, pos token.Pos) []sourceAnchor {
	// External declarations remain useful binding targets but must not expose
	// machine-specific source paths as if they were repository evidence.
	if !pos.IsValid() {
		return []sourceAnchor{}
	}
	point := fset.Position(pos)
	rel := relative(root, point.Filename)
	if rel == ".." || strings.HasPrefix(rel, "../") || filepath.IsAbs(rel) {
		return []sourceAnchor{}
	}
	return []sourceAnchor{{File: rel, Line: point.Line, Column: point.Column, ColumnEncoding: "utf8-byte"}}
}

func qualified(fn *types.Func) string {
	// Receiver and full signature disambiguate methods and imported symbols.
	// A function without a package uses the existing builtin namespace.
	pkg := fn.Pkg()
	prefix := "builtin"
	if pkg != nil {
		prefix = pkg.Path()
	}
	qualifier := func(p *types.Package) string { return p.Path() }
	signature, _ := fn.Type().(*types.Signature)
	receiver := ""
	if signature != nil && signature.Recv() != nil {
		receiver = "(" + types.TypeString(signature.Recv().Type(), qualifier) + ")."
	}
	return prefix + "." + receiver + fn.Name() + types.TypeString(fn.Type(), qualifier)
}

func typeQualified(obj *types.TypeName) string {
	if obj.Pkg() == nil {
		return obj.Name()
	}
	return obj.Pkg().Path() + "." + obj.Name()
}

func functionOwner(fn *types.Func) string {
	// Pointer and value methods share the same declared owner type. Dispatch
	// precision belongs to call edges rather than this ownership attribute.
	signature, _ := fn.Type().(*types.Signature)
	if signature == nil || signature.Recv() == nil {
		return ""
	}
	receiver := signature.Recv().Type()
	if pointer, ok := receiver.(*types.Pointer); ok {
		receiver = pointer.Elem()
	}
	named, ok := receiver.(*types.Named)
	if !ok || named.Obj() == nil {
		return ""
	}
	return typeQualified(named.Obj())
}

func functionKind(fn *types.Func) string {
	if functionOwner(fn) != "" {
		return "method"
	}
	return "function"
}

func functionAttributes(fn *types.Func) map[string]interface{} {
	owner := functionOwner(fn)
	if owner == "" {
		return map[string]interface{}{}
	}
	return map[string]interface{}{"owner": owner}
}

// analyzer owns one JSONL publication. Sharing the emitted set across declaration
// and call traversal keeps external targets from being published more than once.
// The ordered package slice also bounds interface candidates to this request.
type analyzer struct {
	root      string
	buildUnit string
	fset      *token.FileSet
	ordered   []*packageUnit
	prov      provenance
	emitted   map[string]bool
}

// parsePackages preserves request file order and skips the same unparseable
// files as the original entry point. All units share one token.FileSet so source
// positions remain valid across imports, declarations, and call sites.
func parsePackages(requests []packageRequest, fset *token.FileSet) ([]*packageUnit, map[string]*packageUnit) {
	units := make(map[string]*packageUnit)
	var ordered []*packageUnit
	for _, request := range requests {
		var parsedFiles []*ast.File
		for _, name := range request.Files {
			parsed, parseErr := parser.ParseFile(fset, name, nil, parser.SkipObjectResolution)
			if parseErr == nil {
				parsedFiles = append(parsedFiles, parsed)
			}
		}
		if request.ImportPath == "" || len(parsedFiles) == 0 {
			continue
		}
		unit := &packageUnit{
			dir: request.Directory, importPath: request.ImportPath,
			project: request.Project, files: parsedFiles,
		}
		units[request.ImportPath] = unit
		ordered = append(ordered, unit)
	}
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].importPath < ordered[j].importPath })
	return ordered, units
}

// emitNode retains the first observation of each stable identity. Candidate
// attributes must therefore be supplied at the first publication site, exactly
// as for compiler-bound declarations; later references do not rewrite nodes.
func (a *analyzer) emitNode(id, kind, qname string, pos token.Pos, attrs map[string]interface{}) {
	if a.emitted[id] {
		return
	}
	a.emitted[id] = true
	anchors := anchorFor(a.root, a.fset, pos)
	emit(map[string]interface{}{
		"recordKind": "node", "id": id, "kind": kind, "language": "go",
		"qualifiedName": qname, "buildUnitId": a.buildUnit, "sourceAnchors": anchors,
		"attributes": attrs, "provenance": a.prov,
	})
}

// candidateImplementations performs closed-request class hierarchy analysis.
// It checks value receivers before pointer receivers and excludes interface
// declarations themselves. These are candidates, never observed runtime targets.
func (a *analyzer) candidateImplementations(iface *types.Interface, method *types.Func) []*types.Func {
	iface.Complete()
	seen := make(map[string]bool)
	var candidates []*types.Func
	for _, candidateUnit := range a.ordered {
		if candidateUnit.pkg == nil || !candidateUnit.project {
			continue
		}
		scope := candidateUnit.pkg.Scope()
		for _, name := range scope.Names() {
			typeName, ok := scope.Lookup(name).(*types.TypeName)
			if !ok {
				continue
			}
			named, ok := typeName.Type().(*types.Named)
			if !ok {
				continue
			}
			if _, isInterface := named.Underlying().(*types.Interface); isInterface {
				continue
			}
			receiver := types.Type(named)
			if !types.Implements(receiver, iface) {
				receiver = types.NewPointer(named)
				if !types.Implements(receiver, iface) {
					continue
				}
			}
			object, _, _ := types.LookupFieldOrMethod(receiver, true, method.Pkg(), method.Name())
			implementation, ok := object.(*types.Func)
			if !ok {
				continue
			}
			key := qualified(implementation)
			if !seen[key] {
				seen[key] = true
				candidates = append(candidates, implementation)
			}
		}
	}
	sort.Slice(candidates, func(i, j int) bool { return qualified(candidates[i]) < qualified(candidates[j]) })
	return candidates
}

// emitDeclarations preserves the type checker's identities, including receivers.
// Declaration map order is deliberately not part of the JSONL wire contract.
func (a *analyzer) emitDeclarations(unit *packageUnit) {
	for ident, obj := range unit.info.Defs {
		switch value := obj.(type) {
		case *types.TypeName:
			qname := typeQualified(value)
			a.emitNode("go:"+qname, "type", qname, ident.Pos(), map[string]interface{}{})
		case *types.Func:
			qname := qualified(value)
			a.emitNode("go:"+qname, functionKind(value), qname, ident.Pos(), functionAttributes(value))
		}
	}
}

// callBinding distinguishes package selectors from method selections. An
// unresolved object stays unresolved; spelling alone is not binding evidence.
func callBinding(info *types.Info, item *ast.CallExpr) (*types.Func, string, *types.Interface) {
	var obj *types.Func
	dispatch := "static"
	var interfaceType *types.Interface
	switch fun := item.Fun.(type) {
	case *ast.Ident:
		obj, _ = info.Uses[fun].(*types.Func)
	case *ast.SelectorExpr:
		if selection := info.Selections[fun]; selection != nil {
			obj, _ = selection.Obj().(*types.Func)
			if value, ok := selection.Recv().Underlying().(*types.Interface); ok {
				dispatch = "interface"
				interfaceType = value
			} else {
				dispatch = "method"
			}
		} else {
			obj, _ = info.Uses[fun.Sel].(*types.Func)
		}
	}
	return obj, dispatch, interfaceType
}

// emitCalls keeps the enclosing declared function as caller while walking its
// body. Nested expressions are visited by ast.Inspect in their original order.
func (a *analyzer) emitCalls(unit *packageUnit) {
	for _, parsed := range unit.files {
		for _, declaration := range parsed.Decls {
			function, ok := declaration.(*ast.FuncDecl)
			if !ok || function.Body == nil {
				continue
			}
			callerObject, _ := unit.info.Defs[function.Name].(*types.Func)
			if callerObject == nil {
				continue
			}
			source := "go:" + qualified(callerObject)
			ast.Inspect(function.Body, func(node ast.Node) bool {
				if item, ok := node.(*ast.CallExpr); ok {
					a.emitCall(unit, source, item)
				}
				return true
			})
		}
	}
}

// emitCall publishes the exact declaration edge before any interface candidates.
// Anchors use UTF-8 byte columns and an exclusive end, matching go/token offsets.
// Keeping those coordinates in the identity distinguishes repeated call sites.
func (a *analyzer) emitCall(unit *packageUnit, source string, item *ast.CallExpr) {
	obj, dispatch, interfaceType := callBinding(unit.info, item)
	if obj == nil {
		return
	}
	targetName := qualified(obj)
	target := "go:" + targetName
	a.emitNode(target, functionKind(obj), targetName, obj.Pos(), functionAttributes(obj))
	point := a.fset.Position(item.Pos())
	end := a.fset.Position(item.End())
	anchor := sourceAnchor{
		File: relative(a.root, point.Filename), Line: point.Line, Column: point.Column,
		EndLine: end.Line, EndColumn: end.Column, ColumnEncoding: "utf8-byte",
	}
	emit(map[string]interface{}{
		"recordKind": "edge",
		"id": stable("go-edge", source, target, anchor.File,
			fmt.Sprint(anchor.Line), fmt.Sprint(anchor.Column), fmt.Sprint(anchor.EndLine), fmt.Sprint(anchor.EndColumn)),
		"from":       source, "to": target, "relation": "calls", "resolution": "exact",
		"operation": obj.Name(), "dispatch": dispatch, "contractKey": "", "callSite": anchor,
		"evidence":   []string{"go/types object binding"},
		"attributes": map[string]interface{}{}, "provenance": a.prov,
	})
	if interfaceType != nil {
		a.emitCandidates(interfaceType, obj, source, target, anchor)
	}
}

// emitCandidates retains the declaration target as provenance for each possible
// implementation. Candidate edges never replace the exact interface binding.
func (a *analyzer) emitCandidates(iface *types.Interface, obj *types.Func, source, target string, anchor sourceAnchor) {
	for _, implementation := range a.candidateImplementations(iface, obj) {
		candidateName := qualified(implementation)
		candidate := "go:" + candidateName
		if candidate == target {
			continue
		}
		attributes := functionAttributes(implementation)
		attributes["candidateImplementation"] = true
		a.emitNode(candidate, functionKind(implementation), candidateName, implementation.Pos(), attributes)
		emit(map[string]interface{}{
			"recordKind": "edge",
			"id": stable("go-edge-candidate", source, candidate, anchor.File,
				fmt.Sprint(anchor.Line), fmt.Sprint(anchor.Column), fmt.Sprint(anchor.EndLine), fmt.Sprint(anchor.EndColumn)),
			"from": source, "to": candidate, "relation": "calls", "resolution": "candidate",
			"operation": implementation.Name(), "dispatch": "interface", "contractKey": "", "callSite": anchor,
			"evidence":   []string{"go/types implementation candidate (CHA)"},
			"attributes": map[string]interface{}{"declarationTarget": target}, "provenance": a.prov,
		})
	}
}

// main is the composition boundary: decode the offline package request, complete
// type checking for its import closure, then publish project-owned observations.
// Dependency packages participate in binding without becoming project facts.
func main() {
	if len(os.Args) < 5 {
		fmt.Fprintln(os.Stderr, "usage: modus-go-analyzer ROOT BUILD_UNIT CONTEXT_DIGEST PACKAGES_FILE")
		os.Exit(2)
	}
	root, _ := filepath.Abs(os.Args[1])
	buildUnit, contextDigest := os.Args[2], os.Args[3]
	file, err := os.Open(os.Args[4])
	if err != nil {
		panic(err)
	}
	defer file.Close()
	var requests []packageRequest
	if err := json.NewDecoder(file).Decode(&requests); err != nil {
		panic(err)
	}
	fset := token.NewFileSet()
	ordered, units := parsePackages(requests, fset)
	imp := &projectImporter{units: units, fallback: importer.Default(), fset: fset}
	for _, unit := range ordered {
		_, _ = imp.check(unit)
	}
	a := &analyzer{
		root: root, buildUnit: buildUnit, fset: fset, ordered: ordered,
		prov:    provenance{Provider: "go-types", ProviderVersion: "1", ContextDigest: contextDigest},
		emitted: make(map[string]bool),
	}
	for _, unit := range ordered {
		if unit.info == nil || !unit.project {
			continue
		}
		a.emitDeclarations(unit)
		a.emitCalls(unit)
	}
}
