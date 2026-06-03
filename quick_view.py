#!/usr/bin/env python3
"""Quick database initialization and sample viewer"""

import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_DIR = os.path.join(os.path.dirname(__file__), 'database')
DB_PATH = os.path.join(DB_DIR, 'schema.db')

# Create database if doesn't exist
os.makedirs(DB_DIR, exist_ok=True)

if os.path.exists(DB_PATH):
    print("Database already exists, showing samples...\n")
else:
    print("Creating database and generating sample data...\n")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute('CREATE TABLE IF NOT EXISTS academic_years (academic_year VARCHAR(7) PRIMARY KEY);')
    cursor.execute('CREATE TABLE IF NOT EXISTS schools (school_id INTEGER PRIMARY KEY, school_type VARCHAR(15), school_location VARCHAR(10), teacher_student_ratio DECIMAL(5,3), num_classrooms INTEGER, electricity_available CHAR(1) DEFAULT "N", drinking_water CHAR(1) DEFAULT "N", toilet_facility CHAR(1) DEFAULT "N", internet_available CHAR(1) DEFAULT "N", library_available CHAR(1) DEFAULT "N", playground CHAR(1) DEFAULT "N", child_count INTEGER);')
    cursor.execute('CREATE TABLE IF NOT EXISTS students (student_adhaar VARCHAR(12) PRIMARY KEY, name VARCHAR(100), gender CHAR(1), dob DATE NOT NULL, school_id INTEGER, FOREIGN KEY (school_id) REFERENCES schools(school_id));')
    cursor.execute('CREATE TABLE IF NOT EXISTS social_economic (socio_id INTEGER PRIMARY KEY AUTOINCREMENT, student_adhaar VARCHAR(12) NOT NULL UNIQUE, bpl_card_yn CHAR(1) DEFAULT "N", caste VARCHAR(20), place_of_living VARCHAR(20), FOREIGN KEY (student_adhaar) REFERENCES students(student_adhaar) ON DELETE CASCADE);')
    cursor.execute('CREATE TABLE IF NOT EXISTS family_background (family_id INTEGER PRIMARY KEY AUTOINCREMENT, student_adhaar VARCHAR(12) NOT NULL UNIQUE, occupation VARCHAR(30), parent_status VARCHAR(20), parent_income INTEGER, orphan INTEGER DEFAULT 0, FOREIGN KEY (student_adhaar) REFERENCES students(student_adhaar) ON DELETE CASCADE);')
    cursor.execute('CREATE TABLE IF NOT EXISTS attendance (attendance_id INTEGER PRIMARY KEY AUTOINCREMENT, student_adhaar VARCHAR(12) NOT NULL, academic_year VARCHAR(7) NOT NULL, present_days INTEGER NOT NULL, absent_days INTEGER NOT NULL, roster_day INTEGER NOT NULL, FOREIGN KEY (student_adhaar) REFERENCES students(student_adhaar) ON DELETE CASCADE, FOREIGN KEY (academic_year) REFERENCES academic_years(academic_year));')
    cursor.execute('CREATE TABLE IF NOT EXISTS academic_scores (score_id INTEGER PRIMARY KEY AUTOINCREMENT, student_adhaar VARCHAR(12) NOT NULL, academic_year VARCHAR(7) NOT NULL, marks_obtained INTEGER CHECK(marks_obtained BETWEEN 0 AND 1000), FOREIGN KEY (student_adhaar) REFERENCES students(student_adhaar) ON DELETE CASCADE, FOREIGN KEY (academic_year) REFERENCES academic_years(academic_year));')
    cursor.execute('CREATE TABLE IF NOT EXISTS dropout_records (dropout_id INTEGER PRIMARY KEY AUTOINCREMENT, student_adhaar VARCHAR(12) NOT NULL, academic_year VARCHAR(7) NOT NULL, dropout_status VARCHAR(20) DEFAULT "Active", reason_for_dropout VARCHAR(100), FOREIGN KEY (student_adhaar) REFERENCES students(student_adhaar) ON DELETE CASCADE, FOREIGN KEY (academic_year) REFERENCES academic_years(academic_year));')
    
    # Insert academic years
    for year in ['2021-22', '2022-23', '2023-24']:
        cursor.execute('INSERT OR IGNORE INTO academic_years VALUES (?)', (year,))
    
    # Create schools
    for i in range(1, 51):
        cursor.execute('''INSERT INTO schools VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
            (i, random.choice(['BOYS','GIRLS','CO-EDUCATION']), random.choice(['Rural','Urban']),
             round(random.uniform(1.2, 4.5), 2), random.randint(5, 25),
             random.choice(['Y','N']), random.choice(['Y','N']), random.choice(['Y','N']),
             random.choice(['Y','N']), random.choice(['Y','N']), random.choice(['Y','N']),
             random.randint(200, 1500)))
    
    # Sample names
    first_names = ['Aarav', 'Vivaan', 'Aditya', 'Arjun', 'Ananya', 'Diya', 'Priya', 'Neha', 'Rohan', 'Karan']
    last_names = ['Sharma', 'Kumar', 'Singh', 'Patel', 'Gupta', 'Verma', 'Reddy', 'Nair', 'Menon', 'Desai']
    occupations = ['Farmer', 'Labor', 'Business', 'Teacher', 'Driver', 'Shopkeeper', 'Factory Worker']
    parent_statuses = ['Two Parents', 'Single Mother', 'Single Father', 'Guardian']
    castes = ['SC', 'ST', 'BC', 'General', 'Other']
    places = ['Rural', 'Urban', 'Town']
    
    # Create 20 sample students (instead of 1000 for quick demo)
    print("Creating 20 sample students...\n")
    academic_years = ['2021-22', '2022-23', '2023-24']
    
    for idx in range(1, 21):
        adhaar = str(100000000000 + idx)
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        gender = random.choice(['M', 'F'])
        dob = (datetime.now() - timedelta(days=random.randint(3650, 6570))).strftime('%Y-%m-%d')
        school_id = random.randint(1, 50)
        
        cursor.execute('INSERT INTO students VALUES (?,?,?,?,?)',
            (adhaar, name, gender, dob, school_id))
        
        cursor.execute('INSERT INTO social_economic VALUES (NULL,?,?,?,?)',
            (adhaar, random.choice(['Y','Y','Y','N']), random.choice(castes), random.choice(places)))
        
        cursor.execute('INSERT INTO family_background VALUES (NULL,?,?,?,?,?)',
            (adhaar, random.choice(occupations), random.choice(parent_statuses),
             random.randint(10000, 500000), random.choice([0,0,0,1])))
        
        for year in academic_years:
            roster = random.randint(200, 220)
            absent = random.randint(10, 50)
            marks = random.randint(100, 900)
            
            cursor.execute('INSERT INTO attendance VALUES (NULL,?,?,?,?,?)',
                (adhaar, year, roster-absent, absent, roster))
            
            cursor.execute('INSERT INTO academic_scores VALUES (NULL,?,?,?)',
                (adhaar, year, marks))
            
            dropout_prob = 0.05 + (0.15 if marks < 300 else 0) + (0.25 if absent > 30 else 0)
            status = 'Dropped Out' if random.random() < dropout_prob else 'Active'
            reason = random.choice(['Financial', 'Academic', 'Family', 'Work']) if status == 'Dropped Out' else None
            
            cursor.execute('INSERT INTO dropout_records VALUES (NULL,?,?,?,?)',
                (adhaar, year, status, reason))
    
    conn.commit()
    conn.close()
    print("✓ Database created with 20 sample students\n")

# Display students
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) as count FROM students")
total = cursor.fetchone()['count']

print("="*140)
print(f"📊 SAMPLE STUDENTS FROM DATABASE (Total: {total})")
print("="*140)
print(f"{'#':<3} {'Name':<22} {'Aadhaar':<15} {'Gender':<8} {'Age':<5} {'School':<12} {'Location':<10} {'Attendance':<12} {'Marks':<8} {'Status':<12}")
print("-"*140)

cursor.execute("""
    SELECT 
        s.student_adhaar, s.name, s.gender, 
        CAST((strftime('%Y', 'now') - strftime('%Y', s.dob)) AS INTEGER) as age,
        sc.school_type, sc.school_location,
        a.present_days, a.roster_day,
        ROUND(a.present_days * 100.0 / a.roster_day, 1) as attendance_pct,
        ac.marks_obtained,
        dr.dropout_status
    FROM students s
    LEFT JOIN schools sc ON s.school_id = sc.school_id
    LEFT JOIN attendance a ON s.student_adhaar = a.student_adhaar AND a.academic_year = '2023-24'
    LEFT JOIN academic_scores ac ON s.student_adhaar = ac.student_adhaar AND ac.academic_year = '2023-24'
    LEFT JOIN dropout_records dr ON s.student_adhaar = dr.student_adhaar AND dr.academic_year = '2023-24'
    ORDER BY RANDOM() LIMIT 10
""")

students = cursor.fetchall()
for idx, s in enumerate(students, 1):
    attendance = f"{s['attendance_pct']}%"
    print(f"{idx:<3} {s['name']:<22} {s['student_adhaar']:<15} {s['gender']:<8} {s['age']:<5} {(s['school_type'] or 'N/A'):<12} {(s['school_location'] or 'N/A'):<10} {attendance:<12} {s['marks_obtained'] or 'N/A':<8} {(s['dropout_status'] or 'Active'):<12}")

print("\n" + "="*140)
print("📋 DETAILED VIEW - 3 RANDOM STUDENTS")
print("="*140)

cursor.execute("""
    SELECT 
        s.student_adhaar, s.name, s.gender, s.dob,
        CAST((strftime('%Y', 'now') - strftime('%Y', s.dob)) AS INTEGER) as age,
        sc.school_type, sc.school_location,
        se.bpl_card_yn, se.caste, se.place_of_living,
        fb.parent_status, fb.occupation, fb.parent_income, fb.orphan,
        a.present_days, a.absent_days, a.roster_day,
        ROUND(a.present_days * 100.0 / a.roster_day, 1) as attendance_pct,
        ac.marks_obtained,
        dr.dropout_status, dr.reason_for_dropout
    FROM students s
    LEFT JOIN schools sc ON s.school_id = sc.school_id
    LEFT JOIN social_economic se ON s.student_adhaar = se.student_adhaar
    LEFT JOIN family_background fb ON s.student_adhaar = fb.student_adhaar
    LEFT JOIN attendance a ON s.student_adhaar = a.student_adhaar AND a.academic_year = '2023-24'
    LEFT JOIN academic_scores ac ON s.student_adhaar = ac.student_adhaar AND ac.academic_year = '2023-24'
    LEFT JOIN dropout_records dr ON s.student_adhaar = dr.student_adhaar AND dr.academic_year = '2023-24'
    ORDER BY RANDOM() LIMIT 3
""")

detailed = cursor.fetchall()
for idx, s in enumerate(detailed, 1):
    print(f"\n🎓 STUDENT {idx}: {s['name']}")
    print(f"   Basic Info:")
    print(f"   • Aadhaar: {s['student_adhaar']} | Gender: {s['gender']} | DOB: {s['dob']} (Age: {s['age']})")
    print(f"   • School: {s['school_type']} | Location: {s['school_location']}")
    print(f"   Socio-Economic:")
    print(f"   • BPL Card: {s['bpl_card_yn']} | Caste: {s['caste']} | Living: {s['place_of_living']}")
    print(f"   • Parent: {s['parent_status']} | Occupation: {s['occupation']} | Income: ₹{s['parent_income']:,}")
    print(f"   • Orphan: {'Yes' if s['orphan'] else 'No'}")
    print(f"   Academic (2023-24):")
    print(f"   • Attendance: {s['attendance_pct']}% ({s['present_days']} present, {s['absent_days']} absent)")
    print(f"   • Marks: {s['marks_obtained']}/1000")
    print(f"   • Status: {s['dropout_status']} {f'({s['reason_for_dropout']})' if s['reason_for_dropout'] else ''}")

conn.close()
print("\n" + "="*140)
print("✅ Database is ready to use! Start backend with: uvicorn app:app --reload\n")
