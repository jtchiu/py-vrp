#!flask/bin/python

from __future__ import print_function
from ortools.constraint_solver import pywrapcp
from ortools.constraint_solver import routing_enums_pb2

from flask import Flask, jsonify, request
import pymongo
import config
from bson.objectid import ObjectId
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

###########################
# Problem Data Definition #
###########################
def create_data_model(locations, num_vehicles):
	"""Stores the data for the problem"""
	data = {}
	# Locations in block units
	_locations = locations
			# \
			# [(4, 4), # depot
			# (2, 0), (8, 0), # locations to visit
			# (0, 1), (1, 1),
			# (5, 2), (7, 2),
			# (3, 3), (6, 3),
			# (5, 5), (8, 5),
			# (1, 6), (2, 6),
			# (3, 7), (6, 7),
			# (0, 8), (7, 8)]
	# Multiply coordinates in block units by the dimensions of an average city block, 114m x 80m,
	# to get location coordinates.
	data["locations"] = _locations
	# [(l[0] * 114, l[1] * 80) for l in _locations]
	data["num_locations"] = len(data["locations"])
	data["num_vehicles"] = num_vehicles
	data["depot"] = 0
	return data
#######################
# Problem Constraints #
#######################
def manhattan_distance(position_1, position_2):
	"""Computes the Manhattan distance between two points"""
	return (
		geodesic(position_1, position_2).miles)
def create_distance_callback(data):
	"""Creates callback to return distance between points."""
	_distances = {}

	for from_node in range(data["num_locations"]):
		_distances[from_node] = {}
		for to_node in range(data["num_locations"]):
			if from_node == to_node:
				_distances[from_node][to_node] = 0
			else:
				_distances[from_node][to_node] = (
					manhattan_distance(data["locations"][from_node],
									data["locations"][to_node]))

	def distance_callback(from_node, to_node):
		"""Returns the manhattan distance between the two nodes"""
		return _distances[from_node][to_node]

	return distance_callback
def add_distance_dimension(routing, distance_callback):
	"""Add Global Span constraint"""
	distance = 'Distance'
	maximum_distance = 300000  # Maximum distance per vehicle.
	routing.AddDimension(
		distance_callback,
		0,  # null slack
		maximum_distance,
		True,  # start cumul to zero
		distance)
	distance_dimension = routing.GetDimensionOrDie(distance)
	# Try to minimize the max distance among vehicles.
	distance_dimension.SetGlobalSpanCostCoefficient(100)
###########
# Printer #
###########
def print_solution(data, routing, assignment):
	"""Print routes on console."""
	total_distance = 0
	result = []
	for vehicle_id in range(data["num_vehicles"]):
		index = routing.Start(vehicle_id)
		plan_output = 'Route for vehicle {}:\n'.format(vehicle_id)
		distance = 0
		indices = []
		while not routing.IsEnd(index):
			indices.append(routing.IndexToNode(index))
			plan_output += ' {} ->'.format(routing.IndexToNode(index))
			previous_index = index
			index = assignment.Value(routing.NextVar(index))
			distance += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
		result.append(indices)
		plan_output += ' {}\n'.format(routing.IndexToNode(index))
		plan_output += 'Distance of route: {}mi\n'.format(distance)
		print(plan_output)
		total_distance += distance
	print('Total distance of all routes: {}mi'.format(total_distance))
	return result
########
# Main #
########
def main(locations, num_vehicles):
	"""Entry point of the program"""
	# Instantiate the data problem.
	data = create_data_model(locations, num_vehicles)
	# Create Routing Model
	routing = pywrapcp.RoutingModel(
		data["num_locations"],
		data["num_vehicles"],
		data["depot"])
	# Define weight of each edge
	distance_callback = create_distance_callback(data)
	routing.SetArcCostEvaluatorOfAllVehicles(distance_callback)
	add_distance_dimension(routing, distance_callback)
	# Setting first solution heuristic (cheapest addition).
	search_parameters = pywrapcp.RoutingModel.DefaultSearchParameters()
	search_parameters.first_solution_strategy = (
		routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC) # pylint: disable=no-member
	# Solve the problem.
	assignment = routing.SolveWithParameters(search_parameters)
	result = None
	if assignment:
		result = print_solution(data, routing, assignment)
	return result


app = Flask(__name__)

client = pymongo.MongoClient('mongodb+srv://' + config.dbUser + ':' + config.dbPass + '@cluster0-hsykq.gcp.mongodb.net/')
db = client['users']

@app.route('/addAssignments', methods=['POST'])
def add_assignments():
	campaign_id = request.get_json().get('params', '')['campaignId']
	print(campaign_id)
	campaign_collection = db.campaigns
	campaign = campaign_collection.find_one({"_id": ObjectId(campaign_id)})
	locations = [loc[:2] for loc in campaign['locations']]
	num_vehicles = len(campaign['canvassers'])
	result = main(locations, num_vehicles)
	locations = campaign['locations']
	addresses = []
	for canvasser in result:
		addr = []
		for i in canvasser:
			addr.append(locations[i])
		addresses.append(addr)
	print(result)
	print(addresses)
	assignments_col = db['assignments']
	i = 0
	geolocator = Nominatim(user_agent='super_canvasser')
	campaign_dates = campaign['dates']
	dates = []
	for d in campaign_dates:
		if d[6] is '0':
			new_date = d[:6] + d[7:]
			dates.append(new_date)
		else:
			dates.append(d)
			
	for canvassers in addresses:
		tasks = []
		for lat, lng, addr in canvassers:
			task = {
				'complete': False,
				'lat': lat,
				'lng': lng,
				'locName': geolocator.reverse(str(lat) + ', ' + str(lng)).address,
				'rating': 5,
				'answers': [],
				'notes': 'No Notes',
				'assignmentID': 'foo'
			}
			tasks.append(task)
		assignment = {
			'name': campaign['name'],
			'campaignId': campaign_id,
			'canvasser': campaign['canvassers'][i],
			'dates': dates,
			'tasks': tasks
		}
		assignments_col.insert_one(assignment)
		i += 1

	return campaign_id


@app.route('/editAssignments', methods=['POST'])
def edit_assignments():
	campaign_id = request.get_json().get('params', '')['campaignId']
	print(campaign_id)
	campaign_collection = db.campaigns
	campaign = campaign_collection.find_one({"_id": ObjectId(campaign_id)})
	locations = [loc[:2] for loc in campaign['locations']]
	num_vehicles = len(campaign['canvassers'])
	result = main(locations, num_vehicles)
	locations = campaign['locations']
	addresses = []
	for canvasser in result:
		addr = []
		for i in canvasser:
			addr.append(locations[i])
		addresses.append(addr)
	print(result)
	print(addresses)
	assignments_col = db['assignments']
	i = 0
	for canvassers in addresses:
		tasks = []
		for lat, lng, addr in canvassers:
			task = {
				'complete': False,
				'lat': lat,
				'lng': lng,
				'locName': addr,
				'rating': 5,
				'answers': [],
				'notes': 'No Notes',
				'assignmentID': 'foo'
			}
			tasks.append(task)
		assignment = {
			'name': campaign['name'],
			'campaignId': campaign_id,
			'canvasser': campaign['canvassers'][i],
			'dates': campaign['dates'],
			'tasks': tasks
		}
		assignments_col.insert_one(assignment)
		i += 1

	return campaign_id


if __name__ == '__main__':
	# main()
	app.run(debug=True)
