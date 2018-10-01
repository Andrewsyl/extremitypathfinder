from copy import copy
import pickle

from .graph_search import modified_a_star
from .gui import draw_loaded_map, draw_prepared_map, draw_graph, draw_only_path, draw_with_path
from .helper_classes import *
from .helper_fcts import *


# TODO possible to allow polygon consisting of 2 vertices only(=barrier)? lots of algorithms need at least 3 vertices


# Reference:
#   [1] Vinther, Anders Strand-Holm, Magnus Strand-Holm Vinther, and Peyman Afshani.
#   "Pathfinding in Two-dimensional Worlds"
#   http://www.cs.au.dk/~gerth/advising/thesis/anders-strand-holm-vinther_magnus-strand-holm-vinther.pdf

def load_pickle(path='./map.pickle'):
    print('loading map from:', path)
    with open(path, 'rb') as f:
        return pickle.load(f)


class PolygonEnvironment:
    # class for keeping preloaded map for consecutive path queries
    boundary_polygon: Polygon = None
    holes: List[Polygon] = None

    # TODO find way to not store separate list of all (already stored in the polygons)
    all_edges: List[Edge] = None
    all_vertices: List[Vertex] = None
    all_extremities: List[Vertex] = None

    # boundary_extremities = None
    # hole_extremities = None
    prepared: bool = False
    graph: DirectedHeuristicGraph = None
    temp_graph: DirectedHeuristicGraph = None  # for storing and plotting the graph during a query

    def store(self, boundary_coordinates, list_of_hole_coordinates, validate=False, export_plots=False):
        self.prepared = False
        # 'loading the map
        boundary_coordinates = np.array(boundary_coordinates)
        list_of_hole_coordinates = [np.array(hole_coords) for hole_coords in list_of_hole_coordinates]
        if validate:
            check_data_requirements(boundary_coordinates, list_of_hole_coordinates)

        self.boundary_polygon = Polygon(boundary_coordinates, is_hole=False)
        # IMPORTANT: make a copy of the list instead of linking to the same list (python!)
        self.all_edges = self.boundary_polygon.edges.copy()
        self.all_vertices = self.boundary_polygon.vertices.copy()
        self.all_extremities = self.boundary_polygon.extremities.copy()
        self.holes = []
        for coordinates in list_of_hole_coordinates:
            hole_polygon = Polygon(coordinates, is_hole=True)
            self.holes.append(hole_polygon)
            self.all_extremities += hole_polygon.extremities
            self.all_edges += hole_polygon.edges
            self.all_vertices += hole_polygon.vertices

        if export_plots:
            draw_loaded_map(self)

    def store_gridworld(self):
        # TODO option to input grid world

        # convert gridworld into polygons in a way that coordinates still coincide with grid!
        # -> no conversion of obtained graphs needed!
        # TODO option for smoothing (reduces extremities!)
        raise NotImplementedError()

    def export_pickle(self, path='./map.pickle'):
        print('storing map class in:', path)
        with open(path, 'wb') as f:
            pickle.dump(self, f)
        print('done.\n')

    def translate(self, new_origin):
        self.boundary_polygon.translate(new_origin)
        for hole in self.holes:
            hole.translate(new_origin)

    def find_visible(self, vertex_candidates, edges_to_check):
        """
        # IMPORTANT: self.translate(new_origin=query_vertex) always has to be called before!
            (for computing the angle representations wrt. the query vertex)
        query_vertex: a vertex for which the visibility to the vertices should be checked.
            also non extremity vertices, polygon vertices and vertices with the same coordinates are allowed.
            query point also might lie directly on an edge! (angle = 180deg)

        :param vertex_candidates: the set of all vertices which should be checked for visibility.
            IMPORTANT: is being manipulated, so has to be a copy!

        :param edges_to_check: the set of edges which determine visibility
        :return: a set of tuples of all vertices visible from the query vertex and the corresponding distance
        """

        visible_vertices = set()
        if len(vertex_candidates) == 0:
            return visible_vertices

        priority_edges = set()
        # goal: eliminating all vertices lying 'behind' any edge
        # TODO improvement in combination with priority: process edges roughly in sequence, but still allow jumps
        while len(vertex_candidates) > 0 and len(edges_to_check) > 0:
            # check prioritized items first
            try:
                edge = priority_edges.pop()
                edges_to_check.remove(edge)
            except KeyError:
                edge = edges_to_check.pop()

            vertices_to_check = vertex_candidates.copy()
            # the vertices belonging to the edge itself (its vertices) must not be checked.
            # use discard() instead of remove() to not raise an error (they might not be candidates)
            vertices_to_check.discard(edge.vertex1)
            vertices_to_check.discard(edge.vertex2)
            if len(vertices_to_check) == 0:
                continue

            if edge.vertex1.distance_to_origin == 0.0:
                # vertex1 has the same coordinates as the query vertex
                # (but does not belong to the same polygon, not identical!)
                # do not mark this vertex as visible (would add 0 distance edge in the graph)
                vertex_candidates.discard(edge.vertex1)
                # its angle representation is not defined (no line segment from vertex1 to query vertex!)
                # everything between its neighbouring edges is not visible
                v1, v2 = edge.vertex1.get_neighbours()
                range_less_180 = edge.vertex1.is_extremity
                e1 = edge.vertex1.edge1
                # do not check the other neighbouring edge of vertex1 in the future
                edges_to_check.discard(e1)
                priority_edges.discard(e1)
            elif edge.vertex2.distance_to_origin == 0.0:
                vertex_candidates.discard(edge.vertex2)
                v1, v2 = edge.vertex2.get_neighbours()
                range_less_180 = edge.vertex2.is_extremity
                e1 = edge.vertex2.edge2
                edges_to_check.discard(e1)
                priority_edges.discard(e1)
            else:
                v1, v2 = edge.vertex1, edge.vertex2
                range_less_180 = True

            # for all candidate edges check if there are any candidate vertices (besides the ones belonging to the edge)
            #   within this angle range
            repr1 = v1.get_angle_representation()
            repr2 = v2.get_angle_representation()
            # the "view range" of an edge from a query point (spanned by the two vertices of the edge)
            #   is normally < 180deg,
            # but in the case that the query point directly lies on the edge the angle is 180deg
            vertices_to_check = find_within_range(repr1, repr2, vertices_to_check, angle_range_less_180=range_less_180)
            if len(vertices_to_check) == 0:
                continue

            # if a vertex is farther away from the query point than both vertices of the edge,
            #    it surely lies behind the edge
            max_distance = max(edge.vertex1.distance_to_origin, edge.vertex2.distance_to_origin)
            vertices_behind = set(filter(lambda extr: extr.distance_to_origin > max_distance, vertices_to_check))
            # they do not have to be checked
            # TODO improvement: increase the neighbouring edges' priorities when there were extremities behind
            vertices_to_check.difference_update(vertices_behind)
            if len(vertices_to_check) == 0:
                # also done later, only needed if skipping this edge
                vertex_candidates.difference_update(vertices_behind)
                continue

            # if the edge is closer than both vertices it surely lies in front (
            min_distance = min(edge.vertex1.distance_to_origin, edge.vertex2.distance_to_origin)
            vertices_in_front = set(
                filter(lambda extr: extr.distance_to_origin < min_distance, vertices_to_check))
            # they do not have to be checked (safes computation)
            vertices_to_check.difference_update(vertices_in_front)

            # in any other case it has to be tested if the line segment from query point (=origin) to the vertex v
            #    has an intersection with the current edge p1---p2
            # vertices directly on the edge are allowed (not eliminated)!
            p1 = edge.vertex1.get_coordinates_translated()
            p2 = edge.vertex2.get_coordinates_translated()
            for vertex in vertices_to_check:
                if lies_behind(p1, p2, vertex.get_coordinates_translated()):
                    vertices_behind.add(vertex)
                else:
                    vertices_in_front.add(vertex)

            # vertices behind any edge are not visible
            vertex_candidates.difference_update(vertices_behind)
            # if there are no more candidates left. immediately quit checking edges
            if len(vertex_candidates) == 0:
                return {(e, e.distance_to_origin) for e in visible_vertices}

            # check the neighbouring edges of all vertices which lie in front of the edge next first
            # (prioritize them)
            # they lie in front and hence will eliminate other vertices faster
            # the fewer vertex candidates remain, the faster the procedure
            # TODO improvement: increase priority every time and draw highest priority items
            #   but this involves sorting (expensive for large polygons!)
            #   idea: work with a list of sets, add new set for higher priority
            # TODO test speed impact
            for e in vertices_in_front:
                # only add the neighbour edges to the priority set if they still have to be checked!
                if type(e) == PolygonVertex:
                    # only vertices belonging to polygons have neighbours
                    priority_edges.update(edges_to_check.intersection({e.edge1, e.edge2}))

        # all edges have been checked
        # all remaining vertices were not concealed behind any edge and hence are visible
        visible_vertices.update(vertex_candidates)

        # return a set of tuples: (vertex, distance)
        return {(e, e.distance_to_origin) for e in visible_vertices}

    def prepare(self, export_plots=False):
        # compute the all directly reachable extremities based on visibility
        # compute the distances between all directly reachable extremities
        # store as graph

        # preprocessing the map
        # construct graph of visible (=directly reachable) extremities
        # and optimize graph further at construction time
        self.graph = DirectedHeuristicGraph(self.all_extremities)
        extremities_to_check = set(self.all_extremities)
        # have to run for all (also last one!), because edges might get deleted every loop
        while len(extremities_to_check) > 0:
            query_extremity: PolygonVertex = extremities_to_check.pop()
            # extremities are always visible to each other (bi-directional relation -> undirected graph)
            #  -> do not check extremities which have been checked already
            #  (would only give the same result when algorithms are correct)
            # the extremity itself must not be checked when looking for visible neighbours

            # compute the angle representations and distances for all vertices respective to the query point
            self.translate(new_origin=query_extremity)

            visible_vertices = set()
            candidate_extremities = extremities_to_check.copy()
            # existing edges do not have to be checked again
            candidate_extremities.difference_update(self.graph.get_neighbours_of(query_extremity))
            # these vertices all belong to a polygon
            # direct neighbours of the query vertex are visible
            # neighbouring vertices are reachable with the distance equal to the edge length
            n1, n2 = query_extremity.get_neighbours()
            if n1 in candidate_extremities:
                visible_vertices.add((n1, n1.get_distance_to_origin()))
                candidate_extremities.remove(n1)
            if n2 in candidate_extremities:
                visible_vertices.add((n2, n2.get_distance_to_origin()))
                candidate_extremities.remove(n2)
            # even though candidate_extremities might be empty now
            # must not skip to next loop here, because existing graph edges might get deleted later!
            # if len(candidate_extremities) == 0:

            # eliminate all vertices 'behind' the query point from the candidate set
            # since the query vertex is an extremity the 'outer' angle is < 180 degree
            # then the difference between the angle representation of the two edges has to be < 2.0
            # all vertices within the angle of the two neighbouring edges are not visible (no candidates!)
            # vertices with the same angle representation might be visible!
            repr1 = n1.get_angle_representation()
            repr2 = n2.get_angle_representation()
            candidate_extremities.difference_update(
                find_within_range(repr1, repr2, candidate_extremities, angle_range_less_180=True))

            # as shown in [1, Ch. II 4.4.2 "Property One"] an extremity e1 lying in the area "in front of"
            #   another extremity e2 are never the next vertices in a shortest path coming from e2.
            #   and also in reverse: when coming from e1 everything else than e2 itself can be reached faster
            #   without visiting e2. -> e1 and e2 do not have to be connected in the graph.
            # IMPORTANT: this condition only holds for building the basic visibility graph!
            #   when a query point happens to be an extremity, edges to the (visible) extremities in front
            #   MUST be added to the graph!
            # find extremities which fulfill this condition for the given query extremity
            # print(repr1,repr2)
            repr1 = (repr1 + 2.0) % 4.0  # rotate 180 deg
            repr2 = (repr2 + 2.0) % 4.0
            # print(repr1,repr2)

            # IMPORTANT: check all extremities here, not just current candidates
            temp_candidates = set(self.all_extremities)
            temp_candidates.remove(query_extremity)
            lie_in_front = find_within_range(repr1, repr2, temp_candidates, angle_range_less_180=True)
            # print(query_extremity.coordinates, lie_in_front)
            # already existing edges in the graph have to be removed
            self.graph.remove_multiple_undirected_edges(query_extremity, lie_in_front)
            # do not consider when looking for visible extremities (might actually be visible!)
            candidate_extremities.difference_update(lie_in_front)

            # all edges except the neighbouring edges (handled already) have to be checked
            edges_to_check = set(self.all_edges)
            edges_to_check.remove(query_extremity.edge1)
            edges_to_check.remove(query_extremity.edge2)

            visible_vertices |= self.find_visible(candidate_extremities, edges_to_check)

            self.graph.add_multiple_undirected_edges(query_extremity, visible_vertices)

        self.prepared = True
        if export_plots:
            draw_prepared_map(self)
        # TODO improvement: pre compute shortest paths between all directly reachable extremities. advantages?!
        # does it really safe computations during query time?!

    def find_shortest_path(self, start_coordinates, goal_coordinates, export_plots=False):
        # path planning query:
        # make sure the map has been loaded and prepared
        if self.boundary_polygon is None:
            raise ValueError('No Polygons have been loaded into the map yet.')
        if not self.prepared:
            self.prepare()

        # make sure start and goal are within the boundary polygon and outside of all holes
        def within_map(query_coords):
            # within the boundary polygon and outside of all holes
            x, y = query_coords
            if not inside_polygon(x, y, self.boundary_polygon.coordinates, border_value=True):
                return False
            for hole in self.holes:
                if inside_polygon(x, y, hole.coordinates, border_value=False):
                    return False
            return True

        if not (within_map(start_coordinates) and within_map(goal_coordinates)):
            raise ValueError('start or goal do not lie within the map')

        if start_coordinates == goal_coordinates:
            # start and goal are identical and can be reached instantly
            return [start_coordinates, goal_coordinates], 0.0

        # could check if start and goal nodes have identical coordinates with one of the vertices
        # optimisations for visibility test can be made in this case:
        # for extremities the visibility has already been (except for in front) computed
        # BUT: too many cases possible: e.g. multiple vertices identical to query point...
        # -> always create new query vertices

        # include start and goal vertices in the graph
        start_vertex = Vertex(start_coordinates)
        goal_vertex = Vertex(goal_coordinates)

        # create temporary graph (real copy to not edit the original prepared graph)
        # a shallow copy: constructs a new compound object and then (to the extent possible)
        #   inserts references into it to the objects found in the original.
        self.temp_graph = copy(self.graph)

        # the visibility of all other extremities has to be checked
        # IMPORTANT: check if the goal node is visible from the start node!
        # has to be considered in .find_visible()
        candidates = set(self.all_extremities)
        candidates.add(goal_vertex)

        self.translate(start_vertex)
        # IMPORTANT: manually translate the goal vertex, because it is not part of any polygon
        #   and hence does not get translated automatically
        goal_vertex.mark_outdated()

        visibles_n_distances = self.find_visible(candidates, edges_to_check=set(self.all_edges))

        # IMPORTANT geometrical property of this problem: it is always shortest to directly reach a node
        #   instead of visiting other nodes first (there is never an advantage through reduced edge weight)
        # -> when goal is directly reachable, there can be no other shorter path to it. Terminate
        for v, d in visibles_n_distances:
            if v == goal_vertex:
                vertex_path = [start_vertex, goal_vertex]
                if export_plots:
                    draw_with_path(self, self.temp_graph, goal_vertex, start_vertex, vertex_path)
                    draw_only_path(self, vertex_path)
                return [start_coordinates, goal_coordinates], d

            # add unidirectional edges to the temporary graph
            # since modified a star algorithm returns the shortest path from goal to start
            # add edges in the direction: start <-extremity
            self.temp_graph.add_directed_edge(v, start_vertex, d)

        # start node does not have to be considered, because of the earlier check for the start node
        candidates = set(self.all_extremities)
        self.translate(goal_vertex)
        visibles_n_distances = self.find_visible(candidates, edges_to_check=set(self.all_edges))
        # add edges in the direction: extremity <- goal
        self.temp_graph.add_multiple_directed_edges(goal_vertex, visibles_n_distances)

        # function returns the shortest path from goal to start (computational reasons), so just swap the parameters
        # NOTE: exploiting property 2 from [1] here would be more expensive than beneficial
        vertex_path, distance = modified_a_star(self.temp_graph, start=goal_vertex, goal=start_vertex)
        if export_plots:
            draw_graph(self.temp_graph)
            draw_with_path(self, self.temp_graph, goal_vertex, start_vertex, vertex_path)
            draw_only_path(self, vertex_path)

        del self.temp_graph  # free the memory

        # extract the coordinates from the path
        return [tuple(v.coordinates) for v in vertex_path], distance


if __name__ == "__main__":
    pass

    # TODO command line support. read polygons and holes from .json files?
