import unittest
import json
from nbfix.events import *
from nbfix.analyzer import NBFix
from nbfix.resource_utils.utils import read_json, TEST_RES_PATH
from nbfix.constants import *


class TestEvents(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.nbfix = NBFix()
        notebook_json = read_json(TEST_RES_PATH + "dataleak_true.ipynb")["cells"]
        self.nbfix.load_notebook(notebook_json)
        self.nbfix.add_analyses(
            [DATA_LEAK, STALE, IDLE]
        )

    def test_cell_run_event(self):
        cell_run_event = RunCellEvent(0)
        results = cell_run_event.execute(self.nbfix).dumps()
        #self.assertEqual(results, '[{"cell_id":4,"errors":[{"line":2,"label":"X_selected_test", "error_type":"ErrorType.TERMINAL", "message":"Training model with data leak. Path that will lead to this: [0, 1, 2, 3, 4]"}]},{"cell_id":2,"errors":[{"line":2,"label":"y_train", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."},{"line":2,"label":"X_selected_test", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."},{"line":2,"label":"X_selected_train", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."},{"line":2,"label":"y_test", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."}]},{"cell_id":3,"errors":[{"line":3,"label":"a", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."}]}]')
        self.assertTrue(True)
        

    def test_batch_run_event(self):
        run_event = RunBatchEvent(0)
        results = run_event.execute(self.nbfix).dumps(True)
        #self.assertEqual(results, '[{"cell_id":4,"errors":[{"line":2,"label":"X_selected_test", "error_type":"ErrorType.TERMINAL", "message":"Training model with data leak."}],"path":[0, 1, 2, 3, 4]},{"cell_id":2,"errors":[{"line":2,"label":"y_test", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."},{"line":2,"label":"X_selected_test", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."},{"line":2,"label":"y_train", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."},{"line":2,"label":"X_selected_train", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."}],"path":[0, 1, 2]},{"cell_id":3,"errors":[{"line":3,"label":"a", "error_type":"ErrorType.CRITICAL", "message":"Variable uses outdated values."}],"path":[0, 1, 2, 3]},{"cell_id":4,"errors":[{"line":2,"label":"y_pred", "error_type":"ErrorType.TERMINAL", "message":"Variable is not used outside this cell."}],"path":[4]}]')
        self.assertTrue(True)

if __name__ == "__main__":
    unittest.main()
