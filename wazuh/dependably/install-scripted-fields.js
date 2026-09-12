// Adds the dep_* scripted fields to the wazuh-alerts-* index pattern.
// Paste into the browser console on the Wazuh dashboard (it uses your session), or run the
// equivalent against the saved-objects API.
//
// Why these exist: Wazuh's JSON decoder stringifies every value, so data.dependably.critical
// and friends are indexed as keywords and max()/avg() cannot aggregate them. These parse them
// back to numbers.
//
// Why the containsKey guard: indices written before this feed existed carry no mapping for the
// field, and doc['missing.field'] THROWS rather than returning empty -- one shard_failure per
// old index, which OpenSearch reports as a partial result rather than an error. f.size()==0
// only covers a field that exists and is empty, which is not the same condition.
const SRC = [["dep_critical","critical"],["dep_high","high"],["dep_medium","medium"],
             ["dep_low","low"],["dep_affected","packages_affected"],["dep_total","packages_total"]];

const script = p =>
  `if (!doc.containsKey('${p}')) { return 0; } ` +
  `def f = doc['${p}']; if (f.size() == 0) { return 0; } ` +
  `try { return Integer.parseInt(f.value); } catch (Exception e) { return 0; }`;

const so = await fetch('/api/saved_objects/index-pattern/wazuh-alerts-*',
  {headers:{'osd-xsrf':'true'}}).then(r => r.json());
let fields = JSON.parse(so.attributes.fields).filter(f => !f.name.startsWith('dep_'));
for (const [name, src] of SRC) {
  fields.push({name, type:'number', count:0, scripted:true, searchable:true,
               aggregatable:true, readFromDocValues:false,
               script: script('data.dependably.' + src), lang:'painless'});
}
const r = await fetch('/api/saved_objects/index-pattern/wazuh-alerts-*',
  {method:'PUT', headers:{'Content-Type':'application/json','osd-xsrf':'true'},
   body: JSON.stringify({attributes:{fields: JSON.stringify(fields)}})});
console.log('status', r.status);

// Verify across the FULL index set with no time filter -- a dashboard-sized time window only
// touches today's index and will report success while older shards still fail.
const v = await fetch('/api/console/proxy?path=' + encodeURIComponent('wazuh-alerts-*/_search') +
  '&method=POST', {method:'POST', headers:{'osd-xsrf':'true','Content-Type':'application/json'},
  body: JSON.stringify({size:0, query:{match_all:{}},
    aggs:{c:{max:{script:{source:script('data.dependably.critical'), lang:'painless'}}}}})})
  .then(r => r.json());
console.log('shards', v._shards, 'critical', v.aggregations.c.value);  // failed must be 0
