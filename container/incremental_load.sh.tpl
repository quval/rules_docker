#!/usr/bin/env bash
#
# Copyright 2015 The Bazel Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -eu

# This is a generated file that loads all docker layers built by "docker_build".

function guess_runfiles() {
    if [ -d ${BASH_SOURCE[0]}.runfiles ]; then
        # Runfiles are adjacent to the current script.
        echo "$( cd ${BASH_SOURCE[0]}.runfiles && pwd )"
    else
        # The current script is within some other script's runfiles.
        mydir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
        echo $mydir | sed -e 's|\(.*\.runfiles\)/.*|\1|'
    fi
}

RUNFILES="${PYTHON_RUNFILES:-$(guess_runfiles)}"

DOCKER="%{docker_tool_path}"
DOCKER_FLAGS="%{docker_flags}"

if [[ -z "${DOCKER}" ]]; then
    echo >&2 "error: docker not found; do you need to manually configure the docker toolchain?"
    exit 1
fi

# Create temporary files in which to record things to clean up.
TEMP_FILES="$(mktemp -t 2>/dev/null || mktemp -t 'rules_docker_files')"
TEMP_IMAGES="$(mktemp -t 2>/dev/null || mktemp -t 'rules_docker_images')"
function cleanup() {
  cat "${TEMP_FILES}" | xargs rm -rf> /dev/null 2>&1 || true
  cat "${TEMP_IMAGES}" | xargs "${DOCKER}" ${DOCKER_FLAGS} rmi > /dev/null 2>&1 || true

  rm -rf "${TEMP_FILES}"
  rm -rf "${TEMP_IMAGES}"
}
trap cleanup EXIT


function load_legacy() {
  local tarball="${RUNFILES}/$1"

  # docker load has elision of preloaded layers built in.
  echo "Loading legacy tarball base $1..."
  "${DOCKER}" ${DOCKER_FLAGS} load -i "${tarball}"
}

function join_by() {
  local IFS="$1"
  shift
  echo "$*"
}

function import_config() {
  TAG="$1"
  shift

  local registry_output="$(mktemp)"
  echo "${registry_output}" >> "${TEMP_FILES}"
  "${RUNFILES}/%{registry_tool}" -- "${registry_output}" "image" "$@" &
  local registry_pid=$!

  # If we can do that, symlinking the layer diff blobs into the containerd
  # content dir is a way to skip downloading them, and then keeping the
  # downloaded copy. After creating the snapshot of the image, we don't
  # need the layer blobs anymore, but there's no way to prune the content
  # store. As they aren't really needed, it's OK if the symlinks
  # eventually dangle.
  if [[ -w "/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256" ]]; then
    shift
    while test $# -gt 0
    do
      local diff_id="$(cat "${RUNFILES}/$1")"
      local layer="${RUNFILES}/$2"
      local layer_in_content_store="/var/lib/containerd/io.containerd.content.v1.content/blobs/sha256/${diff_id}"
      if [[ ! -e "${layer_in_content_store}" ]]; then
        if [[ -L "${layer_in_content_store}" ]]; then
          rm "${layer_in_content_store}"
        fi
        ln -s "$(readlink -f "${layer}")" "${layer_in_content_store}"
      fi
    done
  fi

  local ref=$(tail -f "${registry_output}" | head -1)
  "${DOCKER}" pull "${ref}"
  kill "${registry_pid}"

  "${DOCKER}" tag "${ref}" "${TAG}"
  "${DOCKER}" rmi "${ref}"
}

function read_variables() {
  local file="${RUNFILES}/$1"
  local new_file="$(mktemp -t 2>/dev/null || mktemp -t 'rules_docker_new')"
  echo "${new_file}" >> "${TEMP_FILES}"

  # Rewrite the file from Bazel for the form FOO=...
  # to a form suitable for sourcing into bash to expose
  # these variables as substitutions in the tag statements.
  sed -E "s/^([^ ]+) (.*)\$/export \\1='\\2'/g" < ${file} > ${new_file}
  source ${new_file}
}

# Statements initializing stamp variables.
%{stamp_statements}

# List of 'import_config' statements for all images.
# This generated and injected by docker_*.
%{load_statements}

# An optional "docker run" statement for invoking a loaded container.
# This is not executed if the single argument --norun is passed or
# no run_statements are generated (in which case, 'run' is 'False').
if [[ "%{run}" == "True" ]]; then
  docker_args=()
  container_args=()

  # Search remaining params looking for docker and container args.
  #
  # It is assumed that they will follow the pattern:
  # [dockerargs...] -- [container args...]
  #
  # "--norun" is treated as a "virtual" additional parameter to
  # "docker run", since it cannot conflict with any "docker run"
  # arguments.  If "--norun" needs to be passed to the container,
  # it can be safely placed after "--".
  while test $# -gt 0
  do
      case "$1" in
          --norun) # norun as a "docker run" option means exit
              exit
              ;;
          --) # divider between docker and container args
              shift
              container_args=("$@")
              break
              ;;
          *)  # potential "docker run" option
              docker_args+=("$1")
              shift
              ;;
      esac
  done

  # Once we've loaded the images for all layers, we no longer need the temporary files on disk.
  # We can clean up before we exec docker, since the exit handler will no longer run.
  cleanup

  # Bash treats empty arrays as unset variables for the purposes of `set -u`, so we only
  # conditionally add these arrays to our args.
  args=(%{run_statement})
  if [[ ${#docker_args[@]} -gt 0 ]]; then
    args+=("${docker_args[@]}")
  fi
  args+=("%{run_tag}")
  if [[ ${#container_args[@]} -gt 0 ]]; then
    args+=("${container_args[@]}")
  fi

  # This generated and injected by docker_*.
  eval exec "${args[@]}"
fi
