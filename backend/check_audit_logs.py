#!/usr/bin/env python3

from database import Database
import json
from datetime import datetime

def check_audit_logs():
    db = Database()
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get count of audit logs
            cursor.execute("SELECT COUNT(*) FROM audit_logs")
            count = cursor.fetchone()[0]
            print(f"\n{'='*80}")
            print(f"TOTAL AUDIT LOGS: {count}")
            print(f"{'='*80}\n")
            
            if count == 0:
                print("No audit logs found in the database.")
                return
            
            # Get detailed audit logs with candidate information
            cursor.execute("""
                SELECT 
                    a.id,
                    a.candidate_id,
                    a.action,
                    a.details,
                    a.performed_by,
                    a.timestamp,
                    c.sender_name,
                    c.source_email,
                    COALESCE(c.parsed_json->>'full_name', c.sender_name) as candidate_name
                FROM audit_logs a
                LEFT JOIN candidates c ON a.candidate_id = c.id
                ORDER BY a.timestamp DESC 
                LIMIT 20
            """)
            
            results = cursor.fetchall()
            
            print("DETAILED AUDIT TRAIL (Last 20 entries)\n")
            
            for i, row in enumerate(results, 1):
                id, candidate_id, action, details, performed_by, timestamp, sender_name, source_email, candidate_name = row
                
                # Format timestamp
                formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                
                # Header with entry number and timestamp
                print(f"Entry #{i} - {formatted_time}")
                print(f"{'─'*60}")
                
                # Action and performer
                print(f"Action: {action}")
                print(f"Performed By: {performed_by}")
                
                # Candidate information (if available)
                if candidate_id:
                    print(f"Candidate: {candidate_name or 'Unknown'}")
                    if source_email:
                        print(f"Email: {source_email}")
                    print(f"Candidate ID: {candidate_id}")
                else:
                    print(f"System Action (No specific candidate)")
                
                # Details breakdown
                if details:
                    print(f"\nDetails:")
                    format_details(details, action)
                
                print(f"\n{'─'*60}\n")
                
            # Get action summary
            cursor.execute("""
                SELECT 
                    action, 
                    COUNT(*) as count,
                    COUNT(CASE WHEN candidate_id IS NOT NULL THEN 1 END) as candidate_specific
                FROM audit_logs 
                GROUP BY action 
                ORDER BY count DESC
            """)
            
            action_summary = cursor.fetchall()
            print("ACTION SUMMARY")
            print("="*50)
            for action, total_count, candidate_count in action_summary:
                print(f"  {action}: {total_count} times")
                if candidate_count > 0:
                    print(f"     {candidate_count} candidate-specific actions")
            
            # Get candidate processing success rate
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN details->>'processed_successfully' = 'true' THEN 1 END) as successful,
                    COUNT(CASE WHEN details->>'processed_successfully' = 'false' THEN 1 END) as failed,
                    COUNT(*) as total
                FROM audit_logs 
                WHERE action = 'email_processed'
            """)
            
            success_stats = cursor.fetchone()
            if success_stats and success_stats[2] > 0:
                successful, failed, total = success_stats
                success_rate = (successful / total) * 100
                print(f"\nEMAIL PROCESSING STATS")
                print("="*50)
                print(f"Successful: {successful}/{total} ({success_rate:.1f}%)")
                print(f"Failed: {failed}/{total} ({(100-success_rate):.1f}%)")
            
            # Get recent candidate activities
            cursor.execute("""
                SELECT DISTINCT
                    c.sender_name,
                    c.source_email,
                    COUNT(a.id) as total_actions,
                    MAX(a.timestamp) as last_activity
                FROM candidates c
                JOIN audit_logs a ON c.id = a.candidate_id
                GROUP BY c.id, c.sender_name, c.source_email
                ORDER BY last_activity DESC
                LIMIT 5
            """)
            
            candidate_activities = cursor.fetchall()
            if candidate_activities:
                print(f"\nRECENT CANDIDATE ACTIVITIES")
                print("="*50)
                for name, email, actions, last_activity in candidate_activities:
                    formatted_time = last_activity.strftime("%Y-%m-%d %H:%M")
                    print(f"{name or 'Unknown'} ({email})")
                    print(f"{actions} actions, last: {formatted_time}")
                    
    except Exception as e:
        print(f"Error retrieving audit logs: {e}")
        import traceback
        traceback.print_exc()

def format_details(details, action):
    """Format details based on action type"""
    try:
        if action == 'email_received':
            print(f"Filename: {details.get('filename', 'Unknown')}")
            print(f"Sender: {details.get('sender', 'Unknown')}")
            
        elif action == 'email_processed':
            success = details.get('processed_successfully', 'Unknown')
            print(f"Success: {success}")
            print(f"Sender: {details.get('sender_email', 'Unknown')}")
            print(f"Message ID: {details.get('message_id', 'Unknown')}")
            
        elif action == 'screening_completed':
            print(f"Position: {details.get('position', 'Unknown')}")
            print(f"Fit Score: {details.get('fit_score', 'Unknown')}/100")
            print(f"Job ID: {details.get('job_id', 'Unknown')}")
            
        elif action == 'email_processing_started':
            print(f"Message ID: {details.get('message_id', 'Unknown')}")
            if 'timestamp' in details:
                ts = datetime.fromtimestamp(details['timestamp'])
                print(f"Started: {ts.strftime('%Y-%m-%d %H:%M:%S')}")
                
        else:
            # Generic details formatting
            for key, value in details.items():
                if isinstance(value, (dict, list)):
                    print(f"{key}: {json.dumps(value, indent=8)}")
                else:
                    print(f"{key}: {value}")
                    
    except Exception as e:
        print(f"Error formatting details: {e}")
        print(f"Raw: {json.dumps(details, indent=8)}")

if __name__ == "__main__":
    check_audit_logs()