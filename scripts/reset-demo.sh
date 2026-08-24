#!/usr/bin/env bash
# Reset the CFactory demo so the four cards can be run again.
#
# Resets PIPELINE STATE ONLY. It deliberately does NOT delete the
# aifactory/* git branches: those hold the work already produced, and a
# re-run overwrites them anyway. Deleting them would throw away the only
# evidence a previous run actually built something.
#
# Order matters and is the same rule as the full portal wipe: CFactory
# POLLS its producers, so clearing it first just repopulates from them.
# Producers first, CFactory last.
set -euo pipefail

CTX="${CTX:-k3d-factory}"
NS="${NS:-factory}"
PID="${PID:-5d78d4b9-35f9-4445-92c1-78f3ff60a494}"   # aifactory-demo
CARDS="${CARDS:-FCT-1 FCT-2 FCT-3 FCT-4}"

k() { kubectl --context "$CTX" -n "$NS" "$@"; }

# The app container is NOT container 0 — `cred-sync` is. A bare
# `kubectl exec deploy/x` lands in the sidecar and reports an empty
# filesystem, which reads as "already clean".
AIPOD=$(k get pods -l app=aifactory --no-headers | awk '$3=="Running"{print $1; exit}')
CFPOD=$(k get pods -l app=cfactory --no-headers | grep -v frontend | awk '$3=="Running"{print $1; exit}')

echo "== 1. delete the AIFactory tasks for the demo project"
k exec "$AIPOD" -c aifactory -- sh -c "
  ids=\$(curl -sS -m 30 -H \"Authorization: Bearer \${APP_API_TOKEN}\" \
    'http://localhost:3101/api/projects/$PID/tasks' 2>/dev/null \
    | python3 -c 'import sys,json;d=json.load(sys.stdin);ts=d if isinstance(d,list) else d.get(\"tasks\",[]);print(chr(10).join(t.get(\"id\",\"\") for t in ts))')
  n=0
  for id in \$ids; do
    [ -z \"\$id\" ] && continue
    enc=\$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=\"\"))' \"\$id\")
    curl -sS -m 30 -o /dev/null -X DELETE -H \"Authorization: Bearer \${APP_API_TOKEN}\" \
      \"http://localhost:3101/api/tasks/\$enc\" && n=\$((n+1))
  done
  echo \"   deleted \$n task(s)\"
"

echo "== 1b. delete leftover build Jobs"
# Job names come from a TRUNCATED spec title, so a re-run of the same card
# collides with the previous attempt's Job and AIFactory returns
# 409 "jobs.batch ... already exists" -> the dispatch fails with a bare 500.
# The tasks are already gone by this point, so any surviving Job is orphaned.
k delete job -l app.kubernetes.io/part-of=aifactory --ignore-not-found >/dev/null 2>&1 || true
for j in $(k get jobs --no-headers 2>/dev/null | awk '/^factory-aifactory-/{print $1}'); do
  k delete job "$j" --ignore-not-found >/dev/null 2>&1 || true
  echo "   deleted job $j"
done
left=$(k get jobs --no-headers 2>/dev/null | awk '/^factory-aifactory-/{print $1}' | wc -l)
echo "   build Jobs remaining: $left"

echo "== 2. clear the durable job_states (stale rows resurrect tasks via the reconcile loop)"
k exec "$AIPOD" -c aifactory -- python3 -c "
import os, asyncio, asyncpg
async def main():
    u = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://','postgresql://')
    c = await asyncpg.connect(u)
    n = await c.fetchval('SELECT count(*) FROM job_states')
    await c.execute('DELETE FROM job_states')
    print(f'   job_states {n} -> 0'); await c.close()
asyncio.run(main())
"

echo "== 3. reset the cards to backlog and drop their stage runs"
k exec "$CFPOD" -c cfactory -- python3 -c "
import sqlite3, sys
cards = '''$CARDS'''.split()
c = sqlite3.connect('/home/nonroot/.cfactory/cfactory.db')
for ck in cards:
    # stage_runs is the one that matters. Clearing status and correlation_key
    # alone leaves {'code': {'status': 'dispatched'}} behind, and the next
    # dispatch refuses with 409 stage_already_running. '{}' is the column
    # default, i.e. the state of a card nobody has ever dispatched.
    c.execute(
        \"UPDATE cards SET status='backlog', correlation_key=NULL, stage_runs='{}' \"
        \"WHERE card_key=?\", (ck,))
c.execute('DELETE FROM work_items')
c.commit()
bad = [k for (k,) in c.execute(
    \"SELECT card_key FROM cards WHERE card_key IN (%s) AND \"
    \"(status!='backlog' OR correlation_key IS NOT NULL OR stage_runs NOT IN ('{}',''))\"
    % ','.join('?'*len(cards)), cards)]
print('   cards reset:', ', '.join(cards))
print('   work_items  :', c.execute('SELECT count(*) FROM work_items').fetchone()[0])
if bad:
    print('   NOT CLEAN   :', bad); sys.exit(1)
print('   verified    : every card is dispatchable again')
"

echo "== done. Re-run with:  POST /api/cards/<KEY>/actions/code"
