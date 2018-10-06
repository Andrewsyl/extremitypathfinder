import unittest

from math import sqrt
import pytest

from extremitypathfinder.extremitypathfinder import PolygonEnvironment, load_pickle
from .test_helpers import proto_test_case


class MainTest(unittest.TestCase):

    def test_fct(self):
        environment = PolygonEnvironment()

        size_x, size_y = 19, 10
        obstacle_iter = [
            # (x,y),

            # obstacles changing boundary
            (0, 1),
            (1, 1),
            (2, 1),
            (3, 1),

            (17, 9),
            (17, 8),
            (17, 7),

            (17, 5),
            (17, 4),
            (17, 3),
            (17, 2),
            (17, 1),
            (17, 0),

            # hole 1
            (5, 5),
            (5, 6),
            (6, 6),
            (6, 7),
            (7, 7),

            # hole 2
            (7, 5),
        ]
        #
        # size_x, size_y = 5,4
        # obstacle_iter = [
        #     # (x,y),
        #
        #     # obstacles changing boundary
        #     (3, 0),
        #     (3, 1),
        #
        #     # hole 1
        #     (1,2),
        #
        # ]

        environment.store_grid_world(size_x, size_y, obstacle_iter, simplify=False, validate=False, export_plots=False)
        environment.prepare(export_plots=False)

        # TODO

        # test if path distance is correct

        # should stay the same if extremities lie on direct path

        # test if points outside the map are being rejected
        for start_coordinates, goal_coordinates in [
            # outside of map region
            ((-1, 5.0), (17, 0.5)),
            ((17, 0.5), (-1, 5.0)),
            ((20, 5.0), (17, 0.5)),
            ((17, 0.5), (20, 5.0)),
            ((1, -5.0), (17, 0.5)),
            ((17, 0.5), (1, -5.0)),
            ((1, 11.0), (17, 0.5)),
            ((17, 0.5), (1, 11.0)),

            # outside boundary polygon
            ((17.5, 5.0), (17, 0.5)),
            ((17, 0.5), (17.5, 5.0)),
            ((1, 1.5), (17, 0.5)),
            ((17, 0.5), (1, 1.5)),

            # inside hole
            ((6.5, 6.5), (17, 0.5)),
            ((17, 0.5), (6.5, 6.5)),
        ]:
            with pytest.raises(ValueError):
                environment.find_shortest_path(start_coordinates, goal_coordinates, export_plots=False)

        for ((start_coordinates, goal_coordinates), expected_output) in [
            # ((start,goal),(path,distance))
            # identical nodes
            (((15, 5), (15, 5)), ([(15, 5), (15, 5)], 0.0)),

            # directly reachable
            (((15, 5), (15, 6)), ([(15, 5), (15, 6)], 1.0)),
            (((15, 6), (15, 5)), ([(15, 6), (15, 5)], 1.0)),
            (((15, 5), (16, 6)), ([(15, 5), (16, 6)], sqrt(2))),
            (((16, 6), (15, 5)), ([(16, 6), (15, 5)], sqrt(2))),
            # on edge
            (((15, 0), (15, 6)), ([(15, 0), (15, 6)], 6.0)),
            (((15, 6), (15, 0)), ([(15, 6), (15, 0)], 6.0)),
            (((17, 5), (16, 5)), ([(15, 5), (16, 6)], 1.0)),
            (((16, 5), (17, 5)), ([(16, 6), (15, 5)], 1.0)),
            # on edge of hole
            (((7, 8), (7, 9)), ([(7, 8), (7, 9)], 1.0)),
            (((7, 9), (7, 8)), ([(7, 9), (7, 8)], 1.0)),

            # directly reachable through a single vertex (does not change distance!)

        ]:
            # print(input, expected_output, fct(input))
            actual_output = environment.find_shortest_path(start_coordinates, goal_coordinates, export_plots=False)
            if actual_output != expected_output:
                print('input: {} expected: {} got: {}'.format(input, expected_output, actual_output))
            assert actual_output == expected_output

        # points on the polygon edges (vertices) should be accepted!
        # FIXME and have direct connection to all visible extremities!


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(MainTest)
    unittest.TextTestRunner(verbosity=2).run(suite)
    # unittest.main()
