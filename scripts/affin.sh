# show process affinities for running ansible-playbook
who="$1"
[ ! "$who" ] && who=ansible-playbook
for i in $(pgrep -f "$who") ; do taskset -c -p $i ; done|cut -d: -f2|sort -n |uniq -c
