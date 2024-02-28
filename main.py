from flask import Flask, jsonify, request, json, Response
from pymongo import MongoClient
from bson import ObjectId, json_util
import certifi

app = Flask(__name__)
CORS(app)
ca = certifi.where()
mongo_client = MongoClient(
    "mongodb+srv://efladmin:god_is_watching@cluster0.eezohvz.mongodb.net/?retryWrites=true&w=majority",
    tlsCAFile=ca
)


# Define a sample GET API endpoint


@app.route('/sample_api', methods=['GET'])
def get_sample_data():
    # Static JSON data
    sample_data = {
        'message': 'Hello, this is a sample API!',
        'data': [1, 2, 3, 4, 5]
    }

    # Return the JSON response
    return jsonify(sample_data)

# Define a new GET API endpoint that retrieves data from MongoDB based on the collectionName query parameter


@app.route('/get_data', methods=['GET'])
def get_data_from_mongodb():
    # Get the collectionName from the query parameter
    collection_name = request.args.get('collectionName')

    # Check if the collectionName is provided
    if not collection_name:
        return jsonify({'error': 'collectionName is required'}), 400

    # Connect to the MongoDB and retrieve data from the specified collection
    try:
        db = mongo_client['afc2024']
        collection = db[collection_name]
        # You can customize the query as neededß
        data_from_mongo = list(collection.find())
        serialized_data = json_util.dumps(data_from_mongo, default=str)
        parsed_data = json_util.loads(serialized_data)
        #serialized_data = json_util.dumps(data_from_mongo)
        # Deserialize using json_util.loads
        return Response(serialized_data, mimetype="application/json")
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Run the Flask app on http://127.0.0.1:5000/
    app.run()
