import assert from 'node:assert/strict'

// 只给现有宿主锁添加本次真实 tarball；宿主的版本、完整性摘要和 peer 约束保持原样。
// npm ci 校验清单一致性，安装后的 npm ls --all 再检查完整依赖树是否满足声明。
export function createInstallProfile(source, lock, manifest, packedPackage) {
  assert.equal(lock.lockfileVersion, 3, '隔离安装需要 v3 宿主锁文件')
  assert.equal(packedPackage.name, manifest.name, '打包元数据中的包名不一致')
  assert.equal(packedPackage.version, manifest.version, '打包元数据中的版本不一致')
  assert.ok(manifest.integrity, '缺少 tarball 完整性摘要')
  const profile = structuredClone(source)
  const profileLock = structuredClone(lock)
  const packagePath = `node_modules/${packedPackage.name}`
  assert.ok(!profileLock.packages[packagePath], '宿主锁中不能已有待验插件')
  const spec = `file:${manifest.filename}`
  profile.name = profileLock.name = profileLock.packages[''].name = 'modus-dsh-smoke-profile'
  delete profile.dsh
  delete profile.scripts
  profile.dependencies = { ...profile.dependencies, [packedPackage.name]: spec }
  profileLock.packages[''].dependencies = { ...profile.dependencies }
  const entry = {
    version: packedPackage.version,
    resolved: spec,
    integrity: manifest.integrity,
  }
  // 必须使用归档内的声明，registry 验收不能借用当前 checkout 的插件依赖。
  for (const key of [
    'dependencies', 'optionalDependencies', 'peerDependencies', 'peerDependenciesMeta',
    'engines', 'os', 'cpu', 'bin', 'license',
  ]) {
    if (packedPackage[key] !== undefined) entry[key] = structuredClone(packedPackage[key])
  }
  profileLock.packages[packagePath] = entry
  return { profile, profileLock }
}
