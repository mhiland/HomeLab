#!/bin/sh
# Installs the dependably localfile into the Wazuh macOS agent config.
#
# It inserts into the first <ossec_config> block. Appending a separate block also works;
# inserting just keeps one managed stanza that is easy to find and replace.
#
# NOTE: installing the rules on the manager is the other half, and it needs a MANAGER RESTART
# to take effect -- see the README. Neither `GET /rules` nor /logtest will tell you that the
# running analysisd is still on the old ruleset.
#
# Idempotent: re-running replaces the managed stanza rather than adding a second copy.
# Run with sudo. Keeps a timestamped backup next to the config.
set -eu

CONF=/Library/Ossec/etc/ossec.conf
LOGDIR=/usr/local/var/log/dependably-siem
OWNER="${SUDO_USER:-$(id -un)}"
MARK_START="<!-- dependably-siem: managed by install-agent-config.sh, do not edit by hand -->"
MARK_END="<!-- dependably-siem: end -->"

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }

# The poller writes as the logged-in user; logcollector reads as root.
mkdir -p "$LOGDIR"
chown "$OWNER" "$LOGDIR"
chmod 755 "$LOGDIR"

cp -p "$CONF" "$CONF.bak.$(date +%Y%m%d%H%M%S)"

python3 - "$CONF" "$LOGDIR" "$MARK_START" "$MARK_END" <<'PY'
import re, sys
conf, logdir, start, end = sys.argv[1:5]
s = open(conf).read()

# Drop any previous managed stanza, and any whole <ossec_config> block we appended before.
s = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', s, flags=re.S)
s = re.sub(r'<!-- Dependably audit feed for the Mac Studio agent\..*?</ossec_config>\s*', '',
           s, flags=re.S)

stanza = (
    "\n  %s\n"
    "  <localfile>\n"
    "    <log_format>json</log_format>\n"
    "    <location>%s/audit.log</location>\n"
    "  </localfile>\n"
    "  %s\n" % (start, logdir, end)
)

# Insert before the close of the FIRST block, which is the one this agent honours.
i = s.index('</ossec_config>')
s = s[:i] + stanza + s[i:]
open(conf, 'w').write(s)
print("stanza installed inside the first <ossec_config> block")
PY

echo "--- inserted stanza, in context ---"
grep -n -B2 -A6 'dependably-siem: managed' "$CONF" | head -20
echo "--- first </ossec_config> is at line ---"
grep -n '</ossec_config>' "$CONF" | head -1

/Library/Ossec/bin/wazuh-logcollector -t && echo "config test: ok"
env PATH=/usr/bin:/bin:/usr/sbin:/sbin /Library/Ossec/bin/wazuh-control restart >/dev/null
echo "agent restarted; waiting for logcollector to open the file..."
sleep 8
echo "--- does logcollector now open the file? ---"
grep -iE 'analyzing file|dependably-siem' /Library/Ossec/logs/ossec.log | tail -5
echo "analyzing-file count: $(grep -ci 'analyzing file' /Library/Ossec/logs/ossec.log)"
