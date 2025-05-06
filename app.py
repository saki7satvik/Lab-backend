from flask import Flask, jsonify, request
from flask_pymongo import PyMongo
from pymongo import ReturnDocument
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import re
from dotenv import load_dotenv
from functools import wraps
import jwt

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app, resources={r"/api/*": {
    "origins": os.getenv('ALLOWED_ORIGINS', '*'),
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})


# Configuration
default_mongo = "mongodb://localhost:27017/lab_management"
app.config["MONGO_URI"] = os.getenv('MONGO_URI', default_mongo)
app.config["JWT_SECRET"] = os.getenv('JWT_SECRET', 'jwt-secret-key')
app.config["JWT_EXPIRE"] = int(os.getenv('JWT_EXPIRE', '3600'))

mongo = PyMongo(app)

# Helper functions
def generate_token(roll_number: str, team_number: str, role: str) -> str:
    payload = {
        'roll_number': roll_number,
        'team_number': team_number,
        'role': role,
        'exp': datetime.utcnow() + timedelta(seconds=app.config["JWT_EXPIRE"])
    }
    return jwt.encode(payload, app.config["JWT_SECRET"], algorithm='HS256')

def validate_team_number(team_number: str) -> bool:
    return bool(re.match(r'^(IPA|IPR)\d{3}$', team_number, re.IGNORECASE))

def validate_roll_number(roll_number: str) -> bool:
    return bool(re.match(r'^[A-Z]\d{3}$', roll_number))

def standard_response(success: bool = True, message: str = None, data=None, status_code: int = 200):
    return jsonify({'success': success, 'message': message, 'data': data}), status_code

def token_required(role: str = None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            token = auth_header.split(' ')[1] if auth_header.startswith('Bearer ') else None
            if not token:
                return standard_response(False, 'Token is missing', status_code=401)
            try:
                payload = jwt.decode(token, app.config["JWT_SECRET"], algorithms=['HS256'])
                if role and payload.get('role') != role:
                    return standard_response(False, 'Unauthorized access', status_code=403)
                request.current_user = payload
            except jwt.ExpiredSignatureError:
                return standard_response(False, 'Token has expired', status_code=401)
            except jwt.InvalidTokenError:
                return standard_response(False, 'Invalid token', status_code=401)
            return f(*args, **kwargs)
        return wrapper
    return decorator

# ----------------------------- ADMIN ROUTES -----------------------------

@app.route('/api/admin/teams', methods=['POST'])
@token_required('admin')
def create_team():
    data = request.get_json() or {}
    team_number = data.get('ipa_ipr_no', '').upper()
    members_input = data.get('members', [])
    if not validate_team_number(team_number):
        return standard_response(False, 'Invalid team number format', status_code=400)
    if len(members_input) < 1:
        return standard_response(False, 'At least one member required', status_code=400)
    if mongo.db.student_teams.find_one({'ipa_ipr_no': team_number}):
        return standard_response(False, 'Team already exists', status_code=409)

    members = []
    for m in members_input:
        rn = m.get('roll_number', '').upper()
        if not validate_roll_number(rn):
            return standard_response(False, f"Invalid roll number: {rn}", status_code=400)
        members.append({
            'name': m.get('name', ''),
            'roll_number': rn,
            'phone': m.get('phone', ''),
            'email': m.get('email', ''),
            'is_active': True
        })

    team_doc = {
        'ipa_ipr_no': team_number,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
        'members': members,
        'component_requests': [],
        'issued_components': [],
        'return_history': []
    }
    mongo.db.student_teams.insert_one(team_doc)
    return standard_response(True, 'Team created', {'team_number': team_number, 'member_count': len(members)}, 201)

# ----------------------------- STUDENT ROUTES -----------------------------
''' student login '''

@app.route('/api/student/login', methods=['POST'])
def student_login():
    #requesting data
    data = request.get_json() or {}
    roll = data.get('roll_number', '').upper()
    #validating roll number
    if not roll:
        return standard_response(False, 'Roll number required', status_code=400)
    
    #database query to find the team - It retrieves only the matching member's details (members.$) and the team's identifier (ipa_ipr_no).
    team = mongo.db.student_teams.find_one({'members.roll_number': roll}, {'members.$': 1, 'ipa_ipr_no': 1})
    if not team:
        return standard_response(False, 'Invalid roll number', status_code=401)

    student = team['members'][0]
    if not student.get('is_active', True):
        return standard_response(False, 'Account disabled', status_code=403)

    #token generation
    token = generate_token(roll, team['ipa_ipr_no'], 'student')
    return standard_response(True, 'Login successful', {'token': token, 'team_number': team['ipa_ipr_no'], 'student_name': student['name']})

@app.route('/api/student/components', methods=['GET'])
@token_required('student')  # or remove this if you don't want token check yet
def get_components():
    components_cursor = mongo.db.components.find({})
    components = []
    for c in components_cursor:
        components.append({
            'id': c.get('id'),
            'name': c.get('name'),
            'description': c.get('description'),
            'available': c.get('available'),
            'category': c.get('category')
        })
    return standard_response(True, 'Components fetched', components)

# requesting component
@app.route('/api/student/request', methods=['POST'])
@token_required('student')
def create_component_request():
    data = request.get_json() or {}
    comp_id = data.get('component_id')
    qty = int(data.get('quantity', 0))
    notes = data.get('notes', '')
    comp_name = data.get('component_name', 'Unnamed')
    
    if not comp_id or qty < 1:
        return standard_response(False, 'Valid component ID and quantity required', status_code=400)

    comp = mongo.db.components.find_one({'id': comp_id}, {'available': 1})
    if not comp:
        return standard_response(False, 'Component not found', status_code=404)
    if qty > comp['available']:
        return standard_response(False, f'Only {comp["available"]} available', status_code=400)

    year = datetime.utcnow().year
    counter = mongo.db.counters.find_one_and_update(
        {'_id': 'request_id'},
        {'$inc': {'seq': 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    req_id = f"REQ{year}-{counter['seq']:03d}"

    new_req = {
        'request_id': req_id,
        'component_id': comp_id,
        'name': comp_name,
        'quantity': qty,
        'request_date': datetime.utcnow(),
        'requested_by': request.current_user['roll_number'],
        'status': 'pending',
        'notes': notes
    }

    mongo.db.student_teams.update_one(
        {'ipa_ipr_no': request.current_user['team_number']},
        {'$push': {'component_requests': new_req}}
    )

    mongo.db.components.update_one({'id': comp_id}, {'$inc': {'available': -qty}})

    return standard_response(True, 'Request submitted', {'request_id': req_id}, 201)


#student profile
@app.route('/api/student/profile', methods=['GET'])
@token_required('student')
def get_student_profile():
    try:
        # Fetch the team details for the current student
        team = mongo.db.student_teams.find_one(
            {'ipa_ipr_no': request.current_user['team_number']},
            {
                '_id': 0,  # Exclude MongoDB's internal ID
                'ipa_ipr_no': 1,
                'members': 1,
                'component_requests': 1,
                'issued_components': 1,
                'return_history': 1
            }
        )
        if not team:
            return standard_response(False, 'Team not found', status_code=404)

        # Filter the current student's details from the members list
        student_details = next(
            (member for member in team['members'] if member['roll_number'] == request.current_user['roll_number']),
            None
        )
        if not student_details:
            return standard_response(False, 'Student not found in team', status_code=404)

        # Structure the response
        response_data = {
            'team_number': team['ipa_ipr_no'],
            'student_details': student_details,
            'component_requests': team.get('component_requests', []),
            'issued_components': team.get('issued_components', []),
            'return_history': team.get('return_history', [])
        }
        return standard_response(True, 'Profile fetched successfully', response_data)
    except Exception as e:
        app.logger.error(f"Error fetching student profile: {e}")
        return standard_response(False, 'Failed to fetch profile', status_code=500)
    
    
# ----------------------------- INSTRUCTOR ROUTES -----------------------------

@app.route('/api/login/instructor', methods=['POST'])
def instructor_login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    # Default credentials for testing
    default_instructor = {
        'username': 'hema',
        'password': 'admin123',
        'name': 'Hema'
    }

    # Validate username and password
    if username == default_instructor['username'] and password == default_instructor['password']:
        # Generate token with role as 'instructor'
        token = generate_token(username, '', 'instructor')
        return standard_response(True, 'Login successful', {
            'token': token,
            'name': default_instructor['name']
        })

    return standard_response(False, 'Invalid username or password', status_code=401)

@app.route('/api/instructor/teams', methods=['GET'])
@token_required('instructor')  # Ensure only instructors can access this route
def get_instructor_teams():
    try:
        # Fetch all teams with the correct projection
        teams = list(mongo.db.student_teams.find(
            {},
            {
                '_id': 0,
                'ipa_ipr_no': 1,
                'members.name': 1,
                'members.roll_number': 1,
                'members.phone': 1
            }
        ))

        formatted_teams = []
        for team in teams:
            formatted_teams.append({
                'team_number': team['ipa_ipr_no'],
                'members': [
                    {
                        'name': member.get('name', ''),
                        'roll': member.get('roll_number', ''),
                        'phno': member.get('phone', '')
                    }
                    for member in team.get('members', [])
                ]
            })

        return standard_response(True, 'Teams fetched successfully', {'teams': formatted_teams})

    except Exception as e:
        app.logger.error(f"Error fetching teams: {e}")
        return standard_response(False, 'Failed to fetch teams', status_code=500)
    

@app.route('/api/instructor/team/<team_number>', methods=['GET'])
@token_required('instructor')
def get_team_details_alt(team_number):
    team = mongo.db.student_teams.find_one({'ipa_ipr_no': team_number})
    if not team:
        return standard_response(False, 'Team not found', status_code=404)

    # Log the team data to verify structure
    app.logger.info(f"Team data: {team}")

    return jsonify(team)


    
@app.route('/api/instructor/teams/<team_number>', methods=['GET'])
@token_required('instructor')
def get_team_details(team_number):
    try:
        team = mongo.db.student_teams.find_one({'ipa_ipr_no': team_number})
        if not team:
            return standard_response(False, 'Team not found', status_code=404)

        # Format data here as needed
        formatted_team = {
            'members': [
                {
                    'name': m.get('name', ''),
                    'roll': m.get('roll_number', ''),
                    'phno': m.get('phone', '')
                } for m in team.get('members', [])
            ],
            'mentors': [
                {
                    'name': mentor.get('name', ''),
                    'phno': mentor.get('phone', '')
                } for mentor in team.get('mentors', [])
            ],
            'issued': team.get('issued_components', []),
            'requested': team.get('requested_components', []),
            'returned': team.get('returned_components', [])
        }

        return standard_response(True, 'Team details fetched', formatted_team)

    except Exception as e:
        app.logger.error(f"Error: {e}")
        return standard_response(False, 'Server error', status_code=500)

# Fix: Corrected the syntax error in the `update_one` call for decrementing inventory
@app.route('/api/instructor/teams/<team_number>/process-request', methods=['POST'])
@token_required('instructor')
def process_component_request(team_number):
    data = request.get_json() or {}
    request_id = data.get('request_id')
    action = data.get('action')
    current_user = request.current_user  # Instructor details from JWT

    # Validate input
    if not request_id or action not in ['accept', 'reject']:
        return standard_response(False, 'Invalid request', status_code=400)

    try:
        with mongo.cx.start_session() as session:  # Use `mongo.cx` for starting a session
            with session.start_transaction():
                # Find team and request
                team = mongo.db.student_teams.find_one(
                    {'ipa_ipr_no': team_number},
                    session=session
                )
                if not team:
                    return standard_response(False, 'Team not found', status_code=404)

                # Find target request
                request_index, target_request = next(
                    ((i, r) for i, r in enumerate(team['component_requests'])
                     if r['request_id'] == request_id and r['status'] == 'pending'),
                    (None, None)
                )

                if not target_request:
                    return standard_response(False, 'No pending request found', status_code=404)

                # Process rejection
                if action == 'reject':
                    mongo.db.student_teams.update_one(
                        {'ipa_ipr_no': team_number},
                        {
                            '$set': {f'component_requests.{request_index}.status': 'rejected'},
                            '$push': {
                                f'component_requests.{request_index}.resolution': {
                                    'by': current_user['username'],
                                    'at': datetime.utcnow().isoformat()
                                }
                            }
                        },
                        session=session
                    )
                    return standard_response(True, 'Request rejected')

                # Process acceptance
                # Check inventory from components collection
                inventory_item = mongo.db.components.find_one(
                    {'id': target_request['component_id']},
                    session=session
                )
                if not inventory_item or inventory_item['available'] < target_request['quantity']:
                    return standard_response(False, 'Component unavailable', status_code=400)

                # Generate unique issue ID
                issue_id = f"ISS{datetime.utcnow().strftime('%Y%m%d')}-{request_id[-4:]}"  # Fix: Ensure unique issue ID

                # Update inventory (decrement available quantity)
                mongo.db.components.update_one(
                    {'id': target_request['component_id']},
                    {'$inc': {'available': -target_request['quantity']}},
                    session=session  # Fix: Corrected misplaced parenthesis
                )

                # Update team document with request acceptance and issuing
                mongo.db.student_teams.update_one(
                    {'ipa_ipr_no': team_number},
                    {
                        '$set': {
                            f'component_requests.{request_index}.status': 'accepted',
                            f'component_requests.{request_index}.resolution.by': current_user['username'],
                            f'component_requests.{request_index}.resolution.at': datetime.utcnow().isoformat()
                        },
                        '$push': {
                            'issued_components': {
                                'issue_id': issue_id,
                                'component_id': target_request['component_id'],
                                'name': target_request['name'],
                                'quantity': target_request['quantity'],
                                'issue_date': datetime.utcnow().isoformat(),
                                'issued_by': current_user['username'],
                                'expected_return': (datetime.utcnow() + timedelta(days=14)).isoformat(),
                                'status': 'issued'
                            }
                        }
                    },
                    session=session
                )

                return standard_response(True, 'Request processed successfully')

    except Exception as e:
        app.logger.error(f"Transaction failed: {str(e)}")
        return standard_response(False, 'Processing failed', status_code=500)


# Fix: Corrected the `approve_request` function to ensure proper handling of issued components
@app.route('/api/instructor/approve', methods=['POST'])
@token_required('instructor')
def approve_request():
    data = request.get_json() or {}
    team_no = data.get('team_number')
    req_id = data.get('request_id')
    days = int(data.get('return_days', 14))
    if not team_no or not req_id:
        return standard_response(False, 'Missing team_number or request_id', status_code=400)

    team = mongo.db.student_teams.find_one_and_update(
        {'ipa_ipr_no': team_no, 'component_requests.request_id': req_id},
        {
            '$set': {
                'component_requests.$.status': 'approved',
                'component_requests.$.processed_at': datetime.utcnow(),
                'component_requests.$.processed_by': request.current_user['username']
            }
        },
        return_document=ReturnDocument.AFTER
    )
    if not team:
        return standard_response(False, 'Request not found', status_code=404)

    approved = next((r for r in team['component_requests'] if r['request_id'] == req_id), None)
    if not approved:
        return standard_response(False, 'Approved request not found', status_code=404)

    issue_seq = len(team.get('issued_components', [])) + 1
    issue_id = f"ISS{datetime.utcnow().year}-{issue_seq:03d}"
    issued = {
        'issue_id': issue_id,
        'component_id': approved['component_id'],
        'name': approved['name'],
        'quantity': approved['quantity'],
        'issue_date': datetime.utcnow(),
        'issued_by': request.current_user['username'],
        'expected_return': (datetime.utcnow() + timedelta(days=days)).isoformat(),
        'request_id': req_id,
        'status': 'issued'
    }
    mongo.db.student_teams.update_one(
        {'ipa_ipr_no': team_no},
        {'$push': {'issued_components': issued}}
    )
    return standard_response(True, 'Approved and issued', {'issue_id': issue_id, 'expected_return': issued['expected_return']})


# ----------------------------- MAIN -----------------------------

if __name__ == '__main__':
    with app.app_context():
        mongo.db.student_teams.create_index('ipa_ipr_no', unique=True)
        mongo.db.student_teams.create_index('members.roll_number', unique=True)
        mongo.db.student_teams.create_index('component_requests.request_id')
        mongo.db.student_teams.create_index('issued_components.issue_id')
        mongo.db.student_teams.create_index('return_history.return_id')
        if not mongo.db.counters.find_one({'_id': 'request_id'}):
            mongo.db.counters.insert_one({'_id': 'request_id', 'seq': 0})
    app.run(host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', 5000)), debug=os.getenv('DEBUG', '').lower() in ('true', '1'))
