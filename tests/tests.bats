#!/usr/bin/env bats

@test "Swarm v2.2.2" {
  v="$(swarm -v 2>&1 || true )"
  [[ "$v" =~ "2.2.2" ]]
}

@test "Swarmwrapper v0.4.7" {
  v="$(swarmwrapper -V 2>&1 || true )"
  [[ "$v" =~ "0.4.7" ]]
}
