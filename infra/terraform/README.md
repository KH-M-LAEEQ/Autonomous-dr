# Terraform

Empty until Week 20 (`TerraformExecutor`). When you get there:

- one module per DR environment shape, not one giant root module
- `plan` is the `dry_run` implementation, `apply` is `execute`
- remote state in S3 with DynamoDB locking — never local state, three people
  will clobber it
- destroy-after-test automation lands in the same PR as the first `apply`, not later
