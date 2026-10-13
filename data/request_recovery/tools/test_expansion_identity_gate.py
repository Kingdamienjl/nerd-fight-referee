import unittest
from expansion_identity_gate import origin_matches
class OriginGateTests(unittest.TestCase):
 def test_requested_name_must_match_source(self):
  from expansion_identity_gate import title_matches_name
  self.assertTrue(title_matches_name('Akaza (Demon Slayer)', 'Demon Slayer', 'Akaza'))
  self.assertFalse(title_matches_name('Akaza (Demon Slayer)', 'Demon Slayer', 'Tanjiro Kamado'))
  self.assertFalse(title_matches_name('Goku (GT)', 'Dragon Ball', 'Goku (Dragon Ball Super)'))
  self.assertFalse(title_matches_name('Ash', 'Pokemon', 'Ashura'))
 def test_wrong_franchise(self):
  for franchise,origin in [('More DC','[[The Real World]]'),('More DC','[[The Binding of Isaac]]'),('Transformers','[[Dungeons and Dragons]]'),('Transformers','[[Ratchet & Clank]]'),('Horror Icons','[[Unknown]]')]:
   self.assertFalse(origin_matches(franchise,origin))
 def test_matching_franchise(self):
  for franchise,origin in [('More DC','[[DC Comics]]'),('More Marvel','[[Marvel Comics]]'),('More Pokemon','[[Pokémon]]'),('Final Fantasy Expansion','[[Final Fantasy|Final Fantasy VI]]'),('Mega Man','[[Mega Man (Franchise)|Mega Man X]]')]:
   self.assertTrue(origin_matches(franchise,origin))

class CachedIdentityTests(unittest.TestCase):
 def test_cache_evidence_and_page_identity_are_required(self):
  import json,tempfile
  from pathlib import Path
  from types import SimpleNamespace
  from expansion_identity_gate import check_origin
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory)
   profile=SimpleNamespace(franchise='More DC',sources=[{'raw_cache_key':'test','page_id':'123'}])
   self.assertFalse(check_origin(profile,root)[0])
   path=root/'test.json'
   def write(origin,page_id=123):
    path.write_text(json.dumps({'body':{'query':{'pages':[{'pageid':page_id,'revisions':[{'slots':{'main':{'content':origin}}}]}]}}}))
   write("'''Origin:''' [[DC Comics]]")
   self.assertTrue(check_origin(profile,root)[0])
   write("'''Origin''': [[DC Comics]]")
   self.assertTrue(check_origin(profile,root)[0])
   write("'''Origin:''' [[The Real World]]")
   self.assertFalse(check_origin(profile,root)[0])
   write("'''Origin:''' [[DC Comics]]",999)
   self.assertFalse(check_origin(profile,root)[0])
   write("'''Origin:''' [[DC Comics]]")
   record=json.loads(path.read_text())
   pages=record['body']['query']['pages']
   record['body']['query']['pages']={'123': pages[0]}
   path.write_text(json.dumps(record))
   self.assertTrue(check_origin(profile,root)[0])
   for invalid in ['{broken', 'null', '{"body":{"query":{"pages":[null]}}}']:
    path.write_text(invalid)
    self.assertFalse(check_origin(profile,root)[0])
