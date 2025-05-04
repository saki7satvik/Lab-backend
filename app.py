import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# In-memory mock data
components_db = [
    {'id': 1, 'name': 'Resistor', 'available': 10, 'category': 'Electronics'},
    {'id': 2, 'name': 'Capacitor', 'available': 15, 'category': 'Electronics'},
    {'id': 3, 'name': 'Arduino Uno', 'available': 5, 'category': 'Microcontrollers'},
]

users_db = {
    'students': {
        'S1001': {'name': 'Alice Johnson', 'team': 'Alpha'},
        'S1002': {'name': 'Bob Smith', 'team': 'Beta'},
        'S1003': {'name': 'Charlie', 'team': 'Gamma'},
    },
    'instructors': {
        'admin': {'password': 'admin123', 'name': 'Dr. Smith'}
    }
}

# API Endpoints

@app.route('/api/login/student', methods=['POST'])
def student_login():
    data = request.get_json()
    roll_number = data.get('roll_number')
    
    if roll_number in users_db['students']:
        return jsonify({
            'success': True,
            'user': users_db['students'][roll_number],
            'token': f"student-token-{roll_number}"  # Simple token for demo
        })
    return jsonify({'success': False, 'message': 'Invalid roll number'}), 401

@app.route('/api/login/instructor', methods=['POST'])
def instructor_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if username in users_db['instructors'] and users_db['instructors'][username]['password'] == password:
        return jsonify({
            'success': True,
            'user': {'name': users_db['instructors'][username]['name']},
            'token': f"instructor-token-{username}"
        })
    return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/components', methods=['GET'])
def get_components():
    search = request.args.get('search', '').lower()
    category = request.args.get('category')
    
    filtered = [c for c in components_db 
               if search in c['name'].lower() and 
               (not category or c['category'] == category)]
    
    return jsonify({'success': True, 'data': filtered})

@app.route('/api/request', methods=['POST'])
def create_request():
    data = request.get_json()
    component_id = data.get('component_id')
    quantity = data.get('quantity', 1)
    student_id = data.get('student_id')
    
    component = next((c for c in components_db if c['id'] == component_id), None)
    if not component:
        return jsonify({'success': False, 'message': 'Component not found'}), 404
    
    if component['available'] < quantity:
        return jsonify({'success': False, 'message': 'Not enough available'}), 400
    
    return jsonify({
        'success': True,
        'message': 'Request submitted for approval',
        'request_id': 123  # Mock request ID
    })

@app.route('/api/student/profile', methods=['GET'])
def get_student_profile():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer student-token-'):
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
        roll_number = auth_header.split('student-token-')[-1]

        if roll_number not in users_db['students']:
            return jsonify({'success': False, 'message': 'Student not found'}), 404

        student = users_db['students'][roll_number]

        profile = {
            'name': student['name'],
            'roll_number': roll_number,
            'team': student['team'],
            'mentors': [
                {'role': 'Mentor 1', 'name': 'Prof. John', 'contact': 'john@example.com'},
                {'role': 'Mentor 2', 'name': 'Dr. Jane', 'contact': 'jane@example.com'}
            ]
        }

        return jsonify(profile)
    
    except Exception as e:
        app.logger.error(f"Error in profile endpoint: {str(e)}")
        return jsonify({'success': False, 'message': 'Internal server error'}), 500
    
    
# Serve React app in production
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True)
