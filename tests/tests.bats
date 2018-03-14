#!/usr/bin/env bats

@test "Swarm v2.2.2" {
  v="$(swarm -v 2>&1 || true )"
  [[ "$v" =~ "2.2.2" ]]
}
