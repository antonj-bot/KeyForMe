"""Offline tests using synthetic values and fake controls; no API or browser."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.core.vin import should_attempt_vin_lookup, NONBLOCKING_FORMAT_ERRORS
from app.core.options import map_options
from app.core.tabs import TabSpec, ensure_tabs, activate_tab, validate_tabs
from app.core.registry import extend_pipelines

class Control:
    def __init__(self, section, index=None, kind="tab"):
        self.section,self.index,self.kind=section,index,kind
    def count(self):
        if self.kind == "add": return self.section.add_count
        if self.kind == "panel": return 1
        return len(self.section.hrefs) if self.index is None else int(self.index < len(self.section.hrefs))
    def nth(self,index): return Control(self.section,index)
    def get_attribute(self,name, **kwargs):
        if name == "href": return self.section.hrefs[self.index]
        if name == "aria-selected": return "true" if self.section.active == self.index else "false"
        if name == "aria-hidden": return "false" if self.section.active == self.index else "true"
        return None
    def locator(self,selector): return self
    def is_visible(self): return True
    def scroll_into_view_if_needed(self,**kwargs): pass
    def wait_for(self,**kwargs):
        if self.kind == "panel" and kwargs.get("state") == "visible" and self.section.active != self.index:
            raise RuntimeError("Panel inactive")
    def click(self,**kwargs):
        if self.kind == "add":
            self.section.clicks += 1
            for _ in range(self.section.add_amount):
                self.section.hrefs.append("#panel-"+str(len(self.section.hrefs)*7+3))
        else: self.section.active=self.index

class Section:
    def __init__(self):
        self.page=Page(); self.hrefs=["#panel-1"]; self.active=0; self.clicks=0; self.add_count=1; self.add_amount=1
    def count(self): return 1
    def locator(self,selector):
        if selector.startswith("[id="):
            href="#"+json.loads(selector[4:-1])
            return Control(self,self.hrefs.index(href),"panel")
        if "st-nav-add" in selector: return Control(self,kind="add")
        return Control(self)

class Page:
    def is_closed(self): return False
    def wait_for_timeout(self,ms): pass

class CoreTests(unittest.TestCase):
    def test_blank_vin(self): self.assertFalse(should_attempt_vin_lookup(""))
    def test_valid_format(self): self.assertTrue(should_attempt_vin_lookup("1HGCM82633A004352"))
    def test_invalid_default_is_conservative(self): self.assertTrue(should_attempt_vin_lookup("SHORT"))
    def test_invalid_nonblocking(self):
        warnings=[]
        self.assertFalse(should_attempt_vin_lookup("SHORT",policy=NONBLOCKING_FORMAT_ERRORS,warn=warnings.append))
        self.assertEqual(len(warnings),1)
        self.assertNotIn("SHORT",warnings[0])
    def test_forbidden_character(self):
        self.assertFalse(should_attempt_vin_lookup("I"*17,policy=NONBLOCKING_FORMAT_ERRORS))
    def test_commas_are_not_separators(self):
        self.assertEqual(map_options("weather","FOG, SMOG, SMOKE",{"FOG, SMOG, SMOKE":"FOG, SMOG, SMOKE"}),"FOG, SMOG, SMOKE")
    def test_unknown_blocks_whole_field(self):
        notes=[]
        self.assertEqual(map_options("weather","CLEAR;UNKNOWN",{"CLEAR":"CLEAR"},notes),"")
        self.assertTrue(notes)
    def test_alias_expansion_deduplicates(self):
        self.assertEqual(map_options("x","A;B",{"A":"X;Y","B":"Y"}),"X;Y")
    def test_dynamic_panels(self):
        section=Section(); ensure_tabs(Page(),section,3)
        self.assertEqual(section.clicks,2)
        panel=activate_tab(section,3)
        self.assertEqual(panel.index,2)
    def test_existing_tabs_no_click(self):
        section=Section(); ensure_tabs(Page(),section,1)
        self.assertEqual(section.clicks,0)
    def test_ambiguous_add_stops(self):
        section=Section(); section.add_count=2
        with self.assertRaises(RuntimeError): ensure_tabs(Page(),section,2)
        self.assertEqual(section.clicks,0)
    def test_multiple_added_stops(self):
        section=Section(); section.add_amount=2
        with self.assertRaises(RuntimeError): ensure_tabs(Page(),section,2)
        self.assertEqual(section.clicks,1)
    def test_missing_added_tab_no_retry(self):
        section=Section(); section.add_amount=0
        with self.assertRaises(RuntimeError): ensure_tabs(Page(),section,2,spec=TabSpec(timeout_ms=0))
        self.assertEqual(section.clicks,1)
    def test_duplicate_panel_stops(self):
        section=Section(); section.hrefs.append(section.hrefs[0])
        with self.assertRaises(RuntimeError): validate_tabs(section,2)
    def test_disabled_plugin(self):
        with patch("app.state_plugins.PLUGINS",{"XX":SimpleNamespace(ENABLED=False)}):
            self.assertEqual(extend_pipelines({"CA":object()}).keys(),{"CA"})
    def test_enabled_plugin(self):
        adapter=SimpleNamespace(ENABLED=True,extract=lambda p,m:{},fill=lambda p,d:None)
        with patch("app.state_plugins.PLUGINS",{"XX":adapter}):
            self.assertIs(extend_pipelines({})["XX"],adapter)
    def test_duplicate_plugin(self):
        with patch("app.state_plugins.PLUGINS",{"CA":SimpleNamespace(ENABLED=False)}):
            with self.assertRaises(ValueError): extend_pipelines({"CA":object()})

if __name__ == "__main__": unittest.main()
