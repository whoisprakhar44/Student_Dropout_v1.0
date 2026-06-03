#!/usr/bin/env python3
"""
Display sample students from the database
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'schema.db')

def display_students():
    if not os.path.exists(DB_PATH):
        print("❌ Database not found. Start the backend first:")
        print("   uvicorn app:app --reload --host 0.0.0.0 --port 8000")
        return
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get total count
    cursor.execute("SELECT COUNT(*) as count FROM students")
    total = cursor.fetchone()['count']
    
    print("\n" + "="*120)
    print(f"📊 STUDENT DATABASE SAMPLE (Total: {total} students)")
    print("="*120)
    
    # Get sample students with related data
    cursor.execute("""
        SELECT 
            s.student_adhaar,
            s.name,
            s.gender,
            CAST((strftime('%Y', 'now') - strftime('%Y', s.dob)) AS INTEGER) as age,
            sc.school_type as school_type,
            sc.school_location as location,
            se.bpl_card_yn as bpl,
            se.place_of_living,
            fb.parent_status,
            fb.parent_income,
            a.present_days,
            a.roster_day,
            ROUND(a.present_days * 100.0 / a.roster_day, 1) as attendance_pct,
            ac.marks_obtained,
            dr.dropout_status
        FROM students s
        LEFT JOIN schools sc ON s.school_id = sc.school_id
        LEFT JOIN social_economic se ON s.student_adhaar = se.student_adhaar
        LEFT JOIN family_background fb ON s.student_adhaar = fb.student_adhaar
        LEFT JOIN attendance a ON s.student_adhaar = a.student_adhaar AND a.academic_year = '2023-24'
        LEFT JOIN academic_scores ac ON s.student_adhaar = ac.student_adhaar AND ac.academic_year = '2023-24'
        LEFT JOIN dropout_records dr ON s.student_adhaar = dr.student_adhaar AND dr.academic_year = '2023-24'
        LIMIT 15
    """)
    
    students = cursor.fetchall()
    
    print(f"\n{'#':<3} {'Name':<20} {'Aadhaar':<15} {'Age':<4} {'School':<12} {'Location':<8} {'Attendance':<12} {'Marks':<6} {'BPL':<4} {'Status':<12}")
    print("-"*120)
    
    for idx, student in enumerate(students, 1):
        name = student['name'][:20].ljust(20)
        aadhaar = student['student_adhaar'][:15].ljust(15)
        age = str(student['age']).ljust(4)
        school_type = (student['school_type'] or 'N/A')[:12].ljust(12)
        location = (student['location'] or 'N/A')[:8].ljust(8)
        attendance = f"{student['attendance_pct']}%".ljust(12) if student['attendance_pct'] else "N/A".ljust(12)
        marks = str(student['marks_obtained'] or 'N/A')[:6].ljust(6)
        bpl = (student['bpl'] or 'N')[:4].ljust(4)
        status = (student['dropout_status'] or 'Active')[:12].ljust(12)
        
        print(f"{idx:<3} {name} {aadhaar} {age} {school_type} {location} {attendance} {marks} {bpl} {status}")
    
    # Detailed view of first 3 students
    print("\n" + "="*120)
    print("📋 DETAILED VIEW - FIRST 3 STUDENTS")
    print("="*120)
    
    cursor.execute("""
        SELECT 
            s.student_adhaar,
            s.name,
            s.gender,
            s.dob,
            CAST((strftime('%Y', 'now') - strftime('%Y', s.dob)) AS INTEGER) as age,
            sc.school_type,
            sc.school_location,
            se.bpl_card_yn,
            se.caste,
            se.place_of_living,
            fb.parent_status,
            fb.occupation,
            fb.parent_income,
            fb.orphan
        FROM students s
        LEFT JOIN schools sc ON s.school_id = sc.school_id
        LEFT JOIN social_economic se ON s.student_adhaar = se.student_adhaar
        LEFT JOIN family_background fb ON s.student_adhaar = fb.student_adhaar
        LIMIT 3
    """)
    
    detailed = cursor.fetchall()
    
    for idx, student in enumerate(detailed, 1):
        print(f"\n🎓 STUDENT {idx}")
        print(f"  Name:              {student['name']}")
        print(f"  Aadhaar:           {student['student_adhaar']}")
        print(f"  Gender:            {student['gender']}")
        print(f"  DOB:               {student['dob']} (Age: {student['age']})")
        print(f"  School Type:       {student['school_type']} - {student['school_location']}")
        print(f"  BPL Card:          {student['bpl_card_yn']} | Caste: {student['caste']} | Living: {student['place_of_living']}")
        print(f"  Parent Status:     {student['parent_status']} | Occupation: {student['occupation']} | Income: ₹{student['parent_income']:,}")
        print(f"  Orphan:            {'Yes' if student['orphan'] else 'No'}")
        
        # Get their academic data
        cursor.execute("""
            SELECT 
                a.present_days, a.absent_days, a.roster_day,
                ROUND(a.present_days * 100.0 / a.roster_day, 1) as attendance_pct,
                ac.marks_obtained,
                CASE 
                    WHEN ac.marks_obtained < 200 THEN 'Low'
                    WHEN ac.marks_obtained < 500 THEN 'Medium'
                    ELSE 'High'
                END as performance,
                dr.dropout_status,
                dr.reason_for_dropout
            FROM attendance a
            LEFT JOIN academic_scores ac ON a.student_adhaar = ac.student_adhaar AND a.academic_year = ac.academic_year
            LEFT JOIN dropout_records dr ON a.student_adhaar = dr.student_adhaar AND a.academic_year = dr.academic_year
            WHERE a.student_adhaar = ? AND a.academic_year = '2023-24'
        """, (student['student_adhaar'],))
        
        academic = cursor.fetchone()
        if academic:
            print(f"  📚 Academic (2023-24):")
            print(f"     - Attendance: {academic['attendance_pct']}% ({academic['present_days']} present, {academic['absent_days']} absent)")
            print(f"     - Marks: {academic['marks_obtained']}/1000 ({academic['performance']} performance)")
            print(f"     - Status: {academic['dropout_status']}")
            if academic['reason_for_dropout']:
                print(f"     - Reason: {academic['reason_for_dropout']}")
    
    # Statistics
    print("\n" + "="*120)
    print("📈 DATABASE STATISTICS")
    print("="*120)
    
    cursor.execute("SELECT COUNT(*) as count FROM schools")
    schools = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance")
    attendance_records = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM academic_scores")
    score_records = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN dropout_status = 'Dropped Out' THEN 1 ELSE 0 END) as dropped_out
        FROM dropout_records 
        WHERE academic_year = '2023-24'
    """)
    dropout = cursor.fetchone()
    
    cursor.execute("""
        SELECT ROUND(AVG(present_days * 100.0 / roster_day), 1) as avg_att
        FROM attendance
        WHERE academic_year = '2023-24'
    """)
    avg_att = cursor.fetchone()['avg_att']
    
    cursor.execute("""
        SELECT ROUND(AVG(marks_obtained), 1) as avg_marks
        FROM academic_scores
        WHERE academic_year = '2023-24'
    """)
    avg_marks = cursor.fetchone()['avg_marks']
    
    print(f"  Total Students:        {total}")
    print(f"  Total Schools:         {schools}")
    print(f"  Attendance Records:    {attendance_records}")
    print(f"  Score Records:         {score_records}")
    print(f"  Dropped Out (2023-24): {dropout['dropped_out']} ({100*dropout['dropped_out']//dropout['total']}%)")
    print(f"  Avg Attendance:        {avg_att}%")
    print(f"  Avg Marks:             {avg_marks}/1000")
    
    conn.close()
    print("\n" + "="*120)

if __name__ == '__main__':
    display_students()
