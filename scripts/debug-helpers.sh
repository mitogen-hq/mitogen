#
# Bash helpers for debugging.
#

# Tell Ansible to write PID files for the mux and top-level process to CWD.
export MITOGEN_SAVE_PIDS=1


# strace -ff -p $(muxpid)
muxpid() {
    cat .ansible-mux.pid
}

# gdb -p $(anspid)
anspid() {
    cat .ansible-controller.pid
}

# perf top -git $(muxtids)
# perf top -git $(muxtids)
muxtids() {
    ls /proc/$(muxpid)/task | tr \\n ,
}

# perf top -git $(anstids)
anstids() {
    ls /proc/$(anspid)/task | tr \\n ,
}

# ttrace $(muxpid) [.. options ..]
#   strace only threads of PID, not children
ttrace() {
    local pid=$1; shift;
    local s=""
    for i in $(ls /proc/$pid/task) ; do
        s="-p $i $s"
    done
    strace $s "$@"
}
