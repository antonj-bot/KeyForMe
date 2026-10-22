"""Offline orchestration tests. All report values are synthetic."""
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch
from app.browser.engine import fill_form
from app.browser.state_forms import CA,NM,get_form_spec
from app.core.vin import get_vin_policy

class EngineTests(unittest.TestCase):
    def run_engine(self,spec,payload,decoded=False):
        page=Mock(); section=Mock(); frame=Mock(); panel=Mock()
        page.frame_locator.return_value=frame; frame.locator.return_value=section
        with patch("app.browser.engine.get_form_spec",return_value=spec), \
             patch("app.browser.engine.ensure_tabs") as ensure, \
             patch("app.browser.engine.activate_tab",return_value=panel) as activate, \
             patch("app.browser.engine.fill_person") as person, \
             patch("app.browser.engine.fill_field") as field, \
             patch("app.browser.engine.fill_radio") as radio, \
             patch("app.browser.engine.fill_vin",return_value=decoded) as vin:
            warnings=fill_form(page,payload,state=spec.state)
        return page,panel,ensure,activate,person,field,radio,vin,warnings
    def test_nm_two_units(self):
        result=self.run_engine(NM,{"units":[{},{}]})
        self.assertEqual(result[3].call_count,2)
        self.assertEqual([c.args[1] for c in result[3].call_args_list],[1,2])
        self.assertEqual(result[4].call_count,4)
    def test_ca_people_order(self):
        r=self.run_engine(CA,{"units":[{}]})
        self.assertEqual([c.args[3] for c in r[4].call_args_list],["driver","owner"])
    def test_nm_people_order(self):
        r=self.run_engine(NM,{"units":[{}]})
        self.assertEqual([c.args[3] for c in r[4].call_args_list],["owner","driver"])
    def test_fills_linked_panel_not_whole_section(self):
        r=self.run_engine(CA,{"units":[{"vehicle":{"make":"SYNTHETIC"}}]})
        self.assertIs(r[4].call_args.args[0],r[1])
        self.assertIs(r[5].call_args.args[0],r[1])
    def test_decode_skips_report_year(self):
        r=self.run_engine(CA,{"units":[{"vehicle":{"year":"2000","make":"X","model":"Y"}}]},True)
        self.assertEqual(r[5].call_count,0)
    def test_failed_decode_fills_report_year(self):
        r=self.run_engine(CA,{"units":[{"vehicle":{"year":"2000","make":"X","model":"Y"}}]},False)
        self.assertEqual(r[5].call_count,3)
    def test_nm_unknown_other_parties_stop_before_modification(self):
        with patch("app.browser.engine.ensure_tabs") as ensure:
            with self.assertRaises(ValueError):
                fill_form(Mock(),{"units":[{}],"other_parties":[{}]},state="NM")
            ensure.assert_not_called()
    def test_witness_excludes_vehicle_and_injury(self):
        r=self.run_engine(CA,{"units":[{}],"other_parties":[{"role":"WITNESS","party_number":"1","injury_code":"1","first_name":"TEST"}]})
        labels=[c.args[3] for c in r[5].call_args_list]
        self.assertNotIn("other.unit_number",labels)
        self.assertNotIn("other.injury_code",labels)
    def test_native_listener_removed(self):
        r=self.run_engine(CA,{"units":[{}]})
        r[0].on.assert_called_once(); r[0].remove_listener.assert_called_once()
    def test_unknown_state(self):
        with self.assertRaises(ValueError): get_form_spec("XX")
    def test_empty_units(self):
        with self.assertRaises(ValueError): fill_form(Mock(),{"units":[]},state="CA")
    def test_nm_policy_is_central(self):
        self.assertTrue(get_vin_policy("NM").skip_invalid_format)
    def test_ca_policy_remains_conservative(self):
        self.assertFalse(get_vin_policy("CA").skip_invalid_format)
    def test_future_adapter_reuses_workflow(self):
        spec=replace(NM,state="XX")
        r=self.run_engine(spec,{"units":[{},{}]})
        self.assertEqual(r[3].call_count,2)


class InteractionTests(unittest.TestCase):
    def test_nm_invalid_vin_never_waits_for_popup(self):
        from app.browser.vin_lookup import fill_vin
        panel=Mock(); controls=Mock(); panel.locator.return_value=controls; controls.count.return_value=1
        warnings=[]
        with patch("app.browser.vin_lookup.click_popup_ok") as popup:
            self.assertFalse(fill_vin(Mock(),panel,{"vin":"SHORT"},1,NM,warnings))
            popup.assert_not_called()
        controls.first.fill.assert_called_once_with("SHORT",timeout=3000)
        self.assertTrue(warnings)
    def test_valid_vin_uses_shared_confirmation(self):
        from app.browser.vin_lookup import fill_vin
        panel=Mock(); controls=Mock(); panel.locator.return_value=controls; controls.count.return_value=1
        with patch("app.browser.vin_lookup.click_popup_ok",return_value=True) as popup, patch("app.browser.vin_lookup.field_has_value",return_value=True):
            self.assertTrue(fill_vin(Mock(),panel,{"vin":"1HGCM82633A004352"},1,NM,[]))
            popup.assert_called_once()
    def test_exact_dropdown_rejects_unmatched(self):
        from app.browser.controls import fill_control
        control=Mock(); control.evaluate.return_value={"tag":"SELECT","options":[{"value":"A","label":"ALPHA"}]}
        warnings=[]
        fill_control(control,"B","test",NM,warnings)
        control.select_option.assert_not_called()
        self.assertTrue(warnings)
    def test_nm_text_keeps_tab_and_readback(self):
        from app.browser.controls import fill_control
        control=Mock(); control.evaluate.return_value={"tag":"INPUT","options":[]}; control.input_value.return_value="TEST"
        warnings=[]
        fill_control(control,"TEST","test",NM,warnings)
        control.press.assert_called_once_with("Tab",timeout=3000)
        self.assertFalse(warnings)
    def test_ca_prefix_code_is_configured_not_global(self):
        from app.browser.controls import fill_control
        control=Mock(); control.evaluate.return_value={"tag":"SELECT","options":[{"value":"code-a","label":"A - Alpha"}]}; control.input_value.return_value="code-a"
        fill_control(control,"A","test",CA,[])
        control.select_option.assert_called_once_with(value="code-a",timeout=30000)

if __name__=="__main__": unittest.main()
