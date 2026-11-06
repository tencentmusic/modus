# IaC 与声明式配置证据适配

以 Terraform module、Kubernetes/Kustomize/Helm、Ansible role 或部署栈识别单元；从声明、plan、apply、发布和运维入口调查。核对 variable/output、resource dependency、state backend、Provider、secret 注入、环境隔离、漂移、回滚、销毁和验证。

声明描述期望状态，不证明生产环境已经成功部署；工具推导依赖不等于业务所有权，中途失败后的远端资源与 state 残留必须分别核验。
