import unittest
import json
from nbsynth.analyses.dataleak_analysis import DataLeakAnalysis
from nbsynth.analyses.stale_cell_analysis import StaleCellAnalysis
from nbsynth.resource_utils.utils import load_notebook, TEST_RES_PATH
from nbsynth.resource_utils.rsrc_mngr import mngr
from nbsynth.analyzer import NBSynth
from nbsynth.constants import *


class Testnbsynth(unittest.TestCase):
    def setUp(self) -> None:
        self.notebook_json = mngr.grab_local_json(TEST_RES_PATH + "dataleak_true.ipynb")[
            "cells"
        ]
        self.nbsynth = NBSynth()
        self.reference_notebook_IR = load_notebook(self.notebook_json)

    def test_load_notebook(self):
        reference_notebook = load_notebook(self.notebook_json)
        self.nbsynth.load_notebook(self.notebook_json)
        for i in reference_notebook.keys():
            self.assertEqual(reference_notebook[i], self.nbsynth.notebook_IR[i])

    def test_add_analyses(self):
        self.nbsynth.add_analyses([DATA_LEAK])
        self.assertIn(DATA_LEAK, self.nbsynth.active_analyses)
        self.assertIsInstance(
            self.nbsynth.all_analyses[DATA_LEAK], DataLeakAnalysis
        )

        self.nbsynth.add_analyses([STALE, FRESH])
        self.assertIn(STALE, self.nbsynth.active_analyses)
        self.assertIsInstance(
            self.nbsynth.all_analyses[STALE], StaleCellAnalysis
        )

    def test_update_abstract_states(self):
        """
        TODO: Update pickles to match new abstract state model
        """
        # self.nbsynth.add_analyses([constants.DATA_LEAK])

        # cell_0 = self.reference_notebook_IR[0]
        # self.nbsynth.update_abstract_states(cell_0)
        # as_0 = pickle.loads(mngr.grab_remote("abstract_state_0.pickle"))
        # self.assertEqual(as_0, self.nbsynth.active_analyses[constants.DATA_LEAK].abstract_state)

        # cell_1 = self.reference_notebook_IR[1]
        # self.nbsynth.update_abstract_states(cell_1)
        # as_1 = pickle.loads(mngr.grab_remote("abstract_state_1.pickle"))
        # self.assertEqual(as_1, self.nbsynth.active_analyses[constants.DATA_LEAK].abstract_state)

        # cell_2 = self.reference_notebook_IR[2]
        # self.nbsynth.update_abstract_states(cell_2)
        # as_2 = pickle.loads(mngr.grab_remote("abstract_state_2.pickle"))
        # self.assertEqual(as_2, self.nbsynth.active_analyses[constants.DATA_LEAK].abstract_state)

        # cell_3 = self.reference_notebook_IR[3]
        # self.nbsynth.update_abstract_states(cell_3)
        # as_3 = pickle.loads(mngr.grab_remote("abstract_state_3.pickle"))
        # self.assertEqual(as_3, self.nbsynth.active_analyses[constants.DATA_LEAK].abstract_state)

        # cell_4 = self.reference_notebook_IR[4]
        # self.nbsynth.update_abstract_states(cell_4)
        # as_4 = pickle.loads(mngr.grab_remote("abstract_state_4.pickle"))
        # self.assertEqual(as_4, self.nbsynth.active_analyses[constants.DATA_LEAK].abstract_state)

if __name__ == "__main__":
    unittest.main()
    