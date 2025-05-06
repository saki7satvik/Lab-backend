import pymongo
from datetime import datetime

client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["lab_management"]

teams = [
    {
        "ipa_ipr_no": "IPA001",
        "team_name": "Team Alpha",
        "members": [
            {
                "name": "Alice Johnson",
                "roll_number": "S1001",
                "phone_number": "1234567890",
                "email": "alice@college.edu"
            },
            {
                "name": "Bob Smith",
                "roll_number": "S1002",
                "phone_number": "2345678901",
                "email": "bob@college.edu"
            },
            {
                "name": "Charlie Brown",
                "roll_number": "S1003",
                "phone_number": "3456789012",
                "email": "charlie@college.edu"
            },
            {
                "name": "Diana Prince",
                "roll_number": "S1004",
                "phone_number": "4567890123",
                "email": "diana@college.edu"
            },
            {
                "name": "Ethan Hunt",
                "roll_number": "S1005",
                "phone_number": "5678901234",
                "email": "ethan@college.edu"
            },
            {
                "name": "Fiona Gallagher",
                "roll_number": "S1006",
                "phone_number": "6789012345",
                "email": "fiona@college.edu"
            }
        ],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    },
    # Add more teams
]

db.student_teams.insert_many(teams)
print("Database seeded successfully!")