#!flask/bin/python
from flask import Flask, jsonify, request
import pymongo

app = Flask(__name__)

dbUser = 'cse308'
dbPass = 'scott'
client = pymongo.MongoClient('mongodb+srv://' + dbUser + ':' + dbPass + '@cluster0-hsykq.gcp.mongodb.net/')

@app.route('/addAssignments', methods=['POST'])
def addAssignments():
	#campaignId = request.args
	#print(campaignId)
	return request.data


@app.route('/editAssignments', methods=['POST'])
def editAssignments():
	#campaignId = request.args
	#print(campaignId)
	print (request.data)
	return request.data


if __name__ == '__main__':
	app.run(debug=True)
