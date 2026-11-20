#!/usr/bin/env bash
# 从当前仓库构建 Modus Manager 和内嵌该应用的 Apple Silicon wheel。
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "$script_dir/.." && pwd -P)"
desktop_dir="$repo_dir/integrations/desktop"
target="aarch64-apple-darwin"
license="$desktop_dir/LICENSE"

if [[ "$(uname -s)" != Darwin || $# -gt 1 ]]; then
    printf '用法（macOS）：%s [/path/to/signed/modus-manager.app]\n' "$0" >&2
    exit 1
fi
if [[ ! -s "$license" ]]; then
    printf '请从包含 integrations/desktop 的 Modus 源码仓库运行此脚本。\n' >&2
    exit 1
fi

app="${1:-}"
if [[ -z "$app" ]]; then
    # 默认从同一份 checkout 构建，正式发布也可传入已公证的应用。
    printf '==> 从源码构建 Modus Manager\n'
    target_dir="$desktop_dir/src-tauri/target"
    (
        cd -- "$desktop_dir"
        npm ci --no-audit --no-fund
        CARGO_TARGET_DIR="$target_dir" APPLE_SIGNING_IDENTITY="${APPLE_SIGNING_IDENTITY:--}" \
            npm run tauri:build -- --ci --target "$target" --bundles app -- --locked
    )
    app="$target_dir/$target/release/bundle/macos/modus-manager.app"
fi

if [[ ! -x "$app/Contents/MacOS/modus-manager" ]]; then
    printf '找不到可执行的桌面应用：%s\n' "$app" >&2
    exit 1
fi
app="$(cd -- "$app" && pwd -P)"
/usr/bin/codesign --verify --deep --strict "$app"
# 主程序和随包 CLI 均须能在 wheel 声明的 Apple Silicon 环境运行。
for binary in "$app/Contents/MacOS/modus-manager" "$app/Contents/MacOS/skills-manager-cli"; do
    /usr/bin/lipo "$binary" -verify_arch arm64
    minimum="$(/usr/bin/otool -arch arm64 -l "$binary" | awk '$1 == "minos" {print $2}')"
    if [[ "$minimum" != "11.0" ]]; then
        printf '无法为 macOS 11 构建 wheel：%s 的最低版本为 %s\n' "$binary" "$minimum" >&2
        exit 1
    fi
done

stage="$(mktemp -d "${TMPDIR:-/tmp}/modus-macos.XXXXXX")"
trap 'rm -rf -- "$stage"' EXIT
archive="$stage/modus-manager.zip"

printf '==> 封装签名应用\n'
payload="$stage/payload"
mkdir -- "$payload"
cp -- "$license" "$payload/LICENSE"
/usr/bin/ditto "$app" "$payload/modus-manager.app"
/usr/bin/ditto -c -k "$payload" "$archive"

printf '==> 构建内嵌桌面应用的 Apple Silicon wheel\n'
MODUS_MANAGER_ARCHIVE="$archive" uv build --wheel --out-dir "$repo_dir/dist" "$repo_dir"
printf '桌面应用：%s\n' "$app"
