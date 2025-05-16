from flask import Flask, render_template, request, jsonify
import pymysql
import spacy
from groq import Groq
import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Load spaCy model
nlp = spacy.load("en_core_web_sm")

# Initialize Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Database configuration
db = pymysql.connect(
    host="localhost",
    user="root",
    password="root",  # Replace with your MySQL password
    database="ai_app",          # Your DB name
    cursorclass=pymysql.cursors.DictCursor
)
cursor = db.cursor()

# Field mapping - maps natural language phrases to actual column names
field_map = {
    "auto_id": "auto_id",
    "stagename": "stagename",
    "submittedby": "submittedby",
    "submittedbyrole": "submittedbyrole",
    "submitteddatetime": "submitteddatetime",
    "program": "program",
    "donor": "donor",
    "expensemainhead": "expensemainhead",
    "expensesubhead": "expensesubhead",
    "billdate": "billdate",
    "invoiceclaimnumber": "invoiceclaimnumber",
    "invoiceclaimamount": "invoiceclaimamount",
    "accept_reject_cancel": "accept_reject_cancel",
    "remarks": "remarks",
    "summary": "summary",
    "expensetype": "expensetype",
    "vendor": "vendor",
    "dispositiontype": "dispositiontype",
    "assignto": "assignto",
    "audit_started_on": "audit_started_on",
    "audit_created_by": "audit_created_by",
    "sample_to": "sample_to",
    "audit_created_on": "audit_created_on",
    "audit_evaluation_duration": "audit_evaluation_duration",
    "deletedstatus": "deletedstatus",
    "deleted_by": "deleted_by",
    "deleted_on": "deleted_on",
    "level1_submittedby": "level1_submittedby",
    "level1_submittedrole": "level1_submittedrole",
    "initiator": "initiator",
    "program_officer1": "program_officer1",
    "finance_check2": "finance_check2",
    "managing_trustee": "managing_trustee",
    "executive_director": "executive_director",
    "budget_owner": "budget_owner",
    "program_officer2": "program_officer2",
    "entry1": "entry1",
    "entry2": "entry2",
    "paymententryapproval": "paymententryapproval",
    "uploadpaymentinbank": "uploadpaymentinbank",
    "isescalationcyclecomplete": "isescalationcyclecomplete",
    "escalatedlevel": "escalatedlevel",
    "isescalationdone": "isescalationdone",
    "escalationdispositionanswerid": "escalationdispositionanswerid",
    "escalationdisposition": "escalationdisposition",
    "dispositionby": "dispositionby",
    "dispositionbyrole": "dispositionbyrole",
    "stagetransactionid": "stagetransactionid",
    "datatableid": "datatableid",
    "employee": "employee",
    "newvendorname": "newvendorname",
    "ifsc": "ifsc",
    "Next_Approver": "Next_Approver",
    "Role_status": "Role_status",
    "approval_pending_status": "approval_pending_status",
    "status": "status",
    "invoiceclaimamount_Lakhs": "invoiceclaimamount_Lakhs",
    "LastDate": "LastDate",
    "refresh_date": "refresh_date",
    "decision": "decision",
    "from_Role_name": "from_Role_name",
    "to_Role_name": "to_Role_name",
    "to_name": "to_name",
    "Voucher_Aging": "Voucher_Aging",
    "pending_days": "pending_days",
    "Voucher_Aging_bucket": "Voucher_Aging_bucket",
    "Pending_days_bucket": "Pending_days_bucket"
}

# Helper function to match field from input
def get_db_field_from_input(user_input):
    user_input = user_input.lower()
    for key in field_map:
        if key.lower() in user_input:
            return field_map[key]
    return None

# Generate SQL query based on NLP
def generate_sql_query(user_input):
    doc = nlp(user_input)

    base_table = "ai_feed_data_dhwnai"
    select_clause = "*"
    where_clauses = []
    params = []

    # Detect aggregation intent
    aggregate_func = None
    for token in doc:
        if token.text in ["count", "how many"]:
            aggregate_func = "COUNT(*)"
        elif token.text in ["sum", "total", "amount", "claim"]:
            field = get_db_field_from_input(user_input) or "invoiceclaimamount"
            aggregate_func = f"SUM({field})"
        elif token.text in ["max", "highest", "largest"]:
            field = get_db_field_from_input(user_input) or "invoiceclaimamount"
            aggregate_func = f"MAX({field})"
        elif token.text in ["min", "lowest", "smallest"]:
            field = get_db_field_from_input(user_input) or "invoiceclaimamount"
            aggregate_func = f"MIN({field})"
        elif token.text in ["avg", "average"]:
            field = get_db_field_from_input(user_input) or "invoiceclaimamount"
            aggregate_func = f"AVG({field})"

    if aggregate_func:
        select_clause = aggregate_func

    # Extract voucher ID
    voucher_id = None
    for token in doc:
        if '_' in token.text and len(token.text) >= 8:
            voucher_id = token.text.upper()
            where_clauses.append("stagetransactionid = %s")
            params.append(voucher_id)

    # Date filters
    for ent in doc.ents:
        if ent.label_ == "DATE":
            date_str = ent.text
            where_clauses.append("submitteddatetime >= STR_TO_DATE(%s, '%%d %%b %%Y')")
            params.append(date_str)

    # Build final SQL
    sql = f"SELECT {select_clause} FROM {base_table}"
    if where_clauses:
        sql += " WHERE " + " AND ".join(where_clauses)

    return sql, tuple(params), (aggregate_func is not None), voucher_id

# Format results into clean response
def format_results(results, is_aggregate, requested_field=None, voucher_id=None):
    if not results:
        return "No matching records found."

    if is_aggregate:
        value = list(results[0].values())[0] if isinstance(results[0], dict) else results[0]
        return f"📊 Result: `{value}`"

    output = ""
    for row in results[:3]:  # Show up to 3 rows
        if voucher_id:
            output += f"\n📄 Voucher: {row['stagetransactionid']}\n"
        if requested_field:
            output += f"{requested_field}: {row.get(requested_field, 'Not available')}\n"
        else:
            output += f"Status: {row['status']} | Amount: ₹{row.get('invoiceclaimamount', 'N/A')} | Pending Days: {row.get('pending_days', 'N/A')}\n"
    return output.strip()

# Get AI response from Groq
def get_groq_response(prompt):
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are an assistant that helps users understand voucher data. Keep answers short and natural."},
                {"role": "user", "content": prompt}
            ],
            model="llama3-8b-8192",
            max_tokens=150,
            temperature=0.5
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"⚠️ Error with AI: {str(e)}"

# Main bot logic
def get_bot_response(user_input):
    user_input = user_input.lower().strip()

    # Use AI for complex questions
    ai_keywords = ["why", "how", "explain", "summarize", "tell me about"]
    if any(kw in user_input for kw in ai_keywords):
        full_prompt = (
            "User asked:\n"
            f"{user_input}\n\n"
            "if it is a complex question, provide a detailed answer.\n"
            "If it is a simple question, provide a short answer in one line.\n"
            "You may refer to fields like status, submittedby, amount, etc."
        )
        return get_groq_response(full_prompt)

    # Try to parse SQL/NLP
    requested_field = get_db_field_from_input(user_input)

    sql, params, is_aggregate, voucher_id = generate_sql_query(user_input)

    try:
        cursor.execute(sql, params)
        result = cursor.fetchall() if not is_aggregate else cursor.fetchone()
    except Exception as e:
        return f"⚠️ DB error: {e}"

    return format_results(result, is_aggregate, requested_field, voucher_id)

# Flask routes
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/get", methods=["POST"])
def chatbot_response():
    msg = request.form["msg"]
    response = get_bot_response(msg)
    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(debug=True)