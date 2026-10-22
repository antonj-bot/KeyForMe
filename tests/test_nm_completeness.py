"""Offline NM completeness tests; no PDFs, network or real report data."""
import unittest
from unittest.mock import patch, MagicMock
from app.extraction import nm_extractor as nm
from app.nm_models import NMPageExtraction, NMUnit, NMConclusion
from app.core.completeness import missing_units, IncompleteExtractionError

class CompletenessTests(unittest.TestCase):
    def test_missing(self): self.assertEqual(missing_units([1,2],[1]),{2})
    def test_no_two_unit_assumption(self): self.assertEqual(missing_units([1],[1]),set())
    def test_empty_inventory(self):
        with self.assertRaises(IncompleteExtractionError): missing_units([], [1])
    def test_unexpected_unit(self):
        with self.assertRaises(IncompleteExtractionError): missing_units([1],[1,2])
    def run_extraction(self, units, recovery_units=None, uncertain=False):
        calls=[]
        def fake(images,prompt,model,schema=NMPageExtraction):
            calls.append(prompt)
            if schema is nm.NMUnitInventory:
                return nm.NMUnitInventory(unit_numbers=[1,2],uncertain=uncertain)
            if schema is nm.NMConclusion: return NMConclusion()
            if prompt == nm.PAGE_1_PROMPT: return NMPageExtraction(units=[NMUnit(unit_number=1)])
            if prompt == nm.PAGES_2_AND_3_PROMPT:
                return NMPageExtraction(units=[NMUnit(unit_number=n) for n in units])
            return NMPageExtraction(units=[NMUnit(unit_number=n) for n in (recovery_units or [])])
        pdf=MagicMock(); pdf.__len__.return_value=22
        with patch.object(nm.pymupdf,'open') as opened, patch.object(nm,'_image',return_value='synthetic-image'), patch.object(nm,'_extract_images',side_effect=fake):
            opened.return_value.__enter__.return_value=pdf
            result=nm.extract_nm('synthetic.pdf','test-model')
        return result,calls
    def test_complete_no_recovery(self):
        report,calls=self.run_extraction([2])
        self.assertEqual(len(calls),4)
        self.assertEqual([u.unit_number for u in report.units],[1,2])
    def test_missing_recovered_once(self):
        report,calls=self.run_extraction([], [2])
        self.assertEqual(len(calls),5)
        self.assertEqual([u.unit_number for u in report.units],[1,2])
    def test_recovery_still_missing_stops(self):
        with self.assertRaises(IncompleteExtractionError): self.run_extraction([],[])
    def test_uncertain_inventory_stops(self):
        with self.assertRaises(IncompleteExtractionError): self.run_extraction([2],uncertain=True)
    def test_unrequested_recovery_stops(self):
        with self.assertRaises(IncompleteExtractionError): self.run_extraction([],[3])
    def test_duplicate_recovery_stops(self):
        with self.assertRaises(IncompleteExtractionError): self.run_extraction([],[2,2])

if __name__=='__main__': unittest.main()
