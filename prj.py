import os
import io
import zipfile
import json
import webbrowser
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import re
from urllib.parse import urlparse

try:
    from googlesearch import search as _gsearch
    _HAS_GOOGLESEARCH = True
except Exception:
    _HAS_GOOGLESEARCH = False
    _gsearch = None

try:
    import requests
    from bs4 import BeautifulSoup
    _HAS_REQUESTS = True
except Exception:
    _HAS_REQUESTS = False

app = Flask(__name__)

# --- Core URL and APK Analysis Functions ---

# --- Add SAFE_DOMAINS at the top ---
SAFE_DOMAINS = [
    # India - Major Banks
    "sbi.co.in", "hdfcbank.com", "icicibank.com", "axisbank.com", "kotak.com",
    "indusind.com", "yesbank.in", "bankofbaroda.in", "unionbankofindia.co.in",
    "canarabank.com", "idfcfirstbank.com", "federalbank.co.in", "pnbindia.in",
    "centralbankofindia.co.in", "bankofindia.co.in",

    # India - Payment Apps / Wallets (UPI & PPI)
    "phonepe.com", "paytm.com", "google.com/pay", "mobikwik.com", "amazon.in",
    "freecharge.in", "bhimupi.gov.in",
    "yono.sbi", "airtel.in", "flipkart.com", "myntra.com",
    "olacabs.com", "uber.com", "makemytrip.com", "goibibo.com", "redbus.in",
    "irctc.co.in", "oyo.com", "easemytrip.in", "yatra.com", "zomato.com",
    "swiggy.com", "dominos.co.in", "pizzahut.co.in", "bigbasket.com", "blinkit.com",
    "jiomart.com", "grofers.com", "medlife.com", "netmeds.com", "1mg.com",
    "pharmeasy.in", "apollopharmacy.in", "healthkart.com", "myglamm.com", "nykaa.com",
    "mamaearth.in", "thebodyshop.in", "puma.com", "adidas.co.in", "nike.com",
    "reebok.in", "decathlon.in", "myntra.com", "ajio.com", "koovs.com", "jabong.com",
    "shopclues.com", "snapdeal.com", "ebay.in", "aliexpress.com", "indiamart.com",
    "tradeindia.com", "justdial.com", "quikr.com", "olx.in", "cars24.com",
    "cardekho.com", "carwale.com", "bikewale.com", "bookmyshow.com", "insider.in",
    "ticketnew.com", "cinemax.co.in", "pvr.com", "inox.com", "spicinemas.in",
    "famecinemas.com", "pvrcinemas.com", "inoxmovies.com", "bookmyshow.com",
    "ticketgenie.in", "eventjini.com", "payu.in", "razorpay.com", "billdesk.com",
    "ccavenue.com", "payoneer.com", "skrill.com", "neteller.com", "instamojo.com",

    # International - Banks & Payment Services
    "paypal.com", "stripe.com", "venmo.com", "squareup.com", "revolut.com",
    "wise.com", "chase.com", "wellsfargo.com", "bankofamerica.com",
    "citibank.com", "capitalone.com", "usbank.com", "barclays.co.uk",
    "hsbc.co.uk", "natwest.com", "lloydsbank.com", "rbc.com", "td.com",

    # Tech / E-Commerce Apps (trusted for payments)
    "apple.com", "itunes.apple.com", "apps.apple.com", "play.google.com",
    "google.com", "amazon.com", "facebook.com", "whatsapp.com",
    "linkedin.com", "microsoft.com", "alipay.com", "wechat.com", "wise.com",

    # India - Top PPI (Prepaid Payment Instruments)
    "phonepe.com", "paytm.com", "freecharge.in", "mobikwik.com", "amazon.in",
    "sodexo.com", "sodexobenefits.in", "yesspay.in", "gocash.in", "rupeek.com"
]

def _fetch_title(url, timeout=5):
    """
    Best-effort: fetch page <title> for simple keyword checks.
    Only used if 'requests' + 'bs4' are available. Returns '' on any failure.
    """
    if not _HAS_REQUESTS:
        return ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; URL-Scanner/1.0; +https://example.com/bot)"
        }
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code != 200 or not r.content:
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        return title
    except Exception:
        return ""

def perform_url_lookup(url):
    """
    Checks a URL's safety using a real external threat intelligence source.
    You must add your API key and the correct API call below.
    """
    print(f"Performing URL lookup for: {url}")

    is_malicious = False
    details = []

    # === YOU MUST EDIT THIS SECTION TO ADD YOUR API KEY ===
    # 1. Get a free API key from a service like VirusTotal (virustotal.com/gui/my-apikey)
    # 2. Add your key here:
    API_KEY = "1176ba657cc318f4f5088539acb612ba5f25dcde9b6104857797aac57a714a68"
    
    if API_KEY != "YOUR_API_KEY_HERE":
        try:
            url_scan_endpoint = "https://www.virustotal.com/api/v3/urls"
            headers = {
                "x-apikey": API_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            data = {'url': url}

            response = requests.post(url_scan_endpoint, headers=headers, data=data)
            response.raise_for_status()

            response_data = response.json()
            
            analysis_stats = response_data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            if analysis_stats.get("malicious", 0) > 0:
                is_malicious = True
                details.append("This URL was flagged as malicious by the threat intelligence API.")
            else:
                details.append("This URL was not flagged by the threat intelligence API.")
                
        except requests.exceptions.RequestException as e:
            is_malicious = False
            details.append(f"An error occurred during API lookup: {e}")
    else:
        # Fallback to a simple check if no API key is provided
        details.append("No API key provided. Using a basic safety check.")
        malicious_keywords = [
            "login", "verify", "update-account", "security-check", "freemoney", "phishing"
        ]
        
        if any(keyword in url.lower() for keyword in malicious_keywords):
            is_malicious = True
            details.append("The URL contains a suspicious keyword, indicating potential phishing.")

        from urllib.parse import urlparse
        parsed_url = urlparse(url)
        malicious_domains = ["fake-bank-login.com", "scam-alerts.net"]
        if parsed_url.netloc in malicious_domains:
            is_malicious = True
            details.append("The URL's domain is a known malicious domain.")
            
    # === END OF SECTION TO EDIT ===

    if not is_malicious and not details:
        details.append("No suspicious indicators found. The URL appears to be safe.")

    return {
        "is_malicious": is_malicious,
        "details": details
    }


def extract_features(apk_file_path):
    """
    Simulated APK feature extraction. In a real-world scenario, you would parse
    the AndroidManifest.xml and analyze the code.
    """
    print(f"Analyzing APK at: {apk_file_path}")
    
    filename = os.path.basename(apk_file_path)
    # Extract name from filename (e.g., "fakebank_v2.1.0.apk" -> "fakebank_v2.1.0")
    app_name_from_file = os.path.splitext(filename)[0]

    features = {
        "permissions": ["Internet Access", "Read Contacts"],
        "size_kb": os.path.getsize(apk_file_path) / 1024,
        "signature_info": "Verified",
        "app_name": app_name_from_file, # Use the extracted name here
        "package_id": "com.unknown.app",
        "version": "1.0",
        "scanned_on": datetime.now().strftime("%b %d, %Y")
    }

    if "fakebank" in filename.lower():
        features["app_name"] = "FakeBank Pro"
        features["package_id"] = "com.fakebank.pro"
        features["version"] = "2.1.0"
        features["permissions"].extend(["Send SMS", "Access Bank OTPs"])
        features["signature_info"] = "Unverified"
        is_malicious = True
    else:
        is_malicious = False
    
    return features, is_malicious

def classify_apk(features, is_malicious):
    """
    Simulated APK classification logic.
    """
    details = []

    if is_malicious:
        details.append("APK requests suspicious permissions.")
        details.append("APK has an unverified signature, which is a red flag.")
    else:
        details.append("No malicious features found.")

    return {
        "is_malicious": is_malicious,
        "details": details,
        "classification_score": 0.95 if is_malicious else 0.15
    }

def perform_ip_lookup(ip_address):
    """
    Simulated IP address lookup.
    """
    print(f"Performing IP address lookup for: {ip_address}")

    is_malicious = False
    details = []

    malicious_ips = ["1.1.1.1", "2.2.2.2"]

    if ip_address in malicious_ips:
        is_malicious = True
        details.append(f"IP address {ip_address} is listed as a known threat.")
    else:
        details.append(f"IP address {ip_address} is not on our threat list.")

    return {
        "is_malicious": is_malicious,
        "details": details
    }

# --- Flask Endpoints ---
@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Scan for Malicious Apps</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body {
                font-family: 'Inter', sans-serif;
                background-color: #121212;
                color: #e0e0e0;
                background-image: url('/image_d8fefc.jpg');
                background-size: cover;
                background-position: center;
                background-attachment: fixed;
            }
            .card {
                background-color: #1e1e1e;
                border: 1px solid #333;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
            }
            .scan-button {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 0.75rem 1.5rem;
                border-radius: 9999px;
                transition: background-color 0.2s;
            }
            .scan-button:hover {
                background-color: #45a049;
            }
            .spinner {
                border: 4px solid rgba(255, 255, 255, 0.1);
                border-left-color: #4CAF50;
                border-radius: 50%;
                width: 3rem;
                height: 3rem;
                animation: spin 1s linear infinite;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            input[type="text"], select, textarea {
                background-color: #333;
                border: 1px solid #555;
                color: white;
                padding: 0.5rem 1rem;
                border-radius: 0.5rem;
            }
            input[type="file"]::file-selector-button {
                background-color: #444;
                color: white;
                border: 1px solid #555;
                border-radius: 0.5rem;
                padding: 0.5rem 1rem;
                cursor: pointer;
            }
            .report-button, .block-button {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 0.5rem 1rem;
                border-radius: 9999px;
                transition: background-color 0.2s;
                text-decoration: none;
            }
            .report-button:hover, .block-button:hover {
                background-color: #45a049;
            }
            .nav-link {
                background-color: black;
                color: white;
                font-weight: bold;
                padding: 0.5rem 1rem;
                border-radius: 9999px;
                transition: background-color 0.2s;
            }
            .nav-link:hover {
                background-color: #333;
            }
        </style>
    </head>
    <body class="flex flex-col items-center min-h-screen p-8">
        <header class="w-full max-w-7xl flex justify-between items-center mb-12">
            <div></div> <nav>
                <a href="#" id="reportButtonTop" class="nav-link">Report a Scam</a>
            </nav>
        </header>

        <div class="text-center mb-12">
            <h1 class="text-5xl font-bold mb-2 text-white">Scan for Malicious Apps</h1>
            <p class="text-lg text-gray-400">Choose a method below to check for fake banking apps.</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-8 w-full max-w-6xl">
            <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-center justify-between transition-transform transform hover:scale-105">
                <div class="flex flex-col items-center mb-6">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-12 h-12 text-yellow-500 mb-4">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-4.5-9a2.25 2.25 0 0 0-2.25 2.25V12m2.25-10.5h-15a2.25 2.25 0 0 0-2.25 2.25v10.5A2.25 2.25 0 0 0 4.5 21h15a2.25 2.25 0 0 0 2.25-2.25V12m-4.5-9a2.25 2.25 0 0 1 2.25 2.25V12" />
                    </svg>
                    <p class="text-lg font-semibold text-white">Upload APK File</p>
                </div>
                <div class="w-full">
                    <input type="file" id="apkFile" accept=".apk" class="w-full text-sm">
                    <button id="scanFileButton" class="scan-button w-full mt-6">Scan File</button>
                </div>
            </div>

            <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-center justify-between transition-transform transform hover:scale-105">
                <div class="flex flex-col items-center mb-6">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-12 h-12 text-green-500 mb-4">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9 9 0 0 0 8.784-5.464l-.973-.243a8.25 8.25 0 1 1-13.436-5.832" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75c0-1.874.526-3.633 1.455-5.203M12 21v-1.5m8.784-5.464L21.75 16.5m-1.742-.436c1.373-2.583 2.059-5.32 2.059-8.082a9 9 0 0 0-18 0c0 2.762.686 5.499 2.059 8.082m15.539-8.082a9 9 0 0 1-14.542-5.176m14.542 5.176l-1.096-.289a9 9 0 0 0-13.436-5.832" />
                    </svg>
                    <p class="text-lg font-semibold text-white">Enter URL</p>
                </div>
                <div class="w-full">
                    <input type="text" id="urlInput" placeholder="https://example.com/apk" class="w-full">
                    <button id="scanUrlButton" class="scan-button w-full mt-6">Scan URL</button>
                </div>
            </div>

            <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-center justify-between transition-transform transform hover:scale-105">
                <div class="flex flex-col items-center mb-6">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-12 h-12 text-blue-500 mb-4">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 21a9 9 0 0 0 8.784-5.464l-.973-.243a8.25 8.25 0 1 1-13.436-5.832" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.25 15.75c0-1.874.526-3.633 1.455-5.203M12 21v-1.5m8.784-5.464L21.75 16.5m-1.742-.436c1.373-2.583 2.059-5.32 2.059-8.082a9 9 0 0 0-18 0c0 2.762.686 5.499 2.059 8.082m15.539-8.082a9 9 0 0 1-14.542-5.176m14.542 5.176l-1.096-.289a9 9 0 0 0-13.436-5.832" />
                    </svg>
                    <p class="text-lg font-semibold text-white">Enter IP Address</p>
                </div>
                <div class="w-full">
                    <input type="text" id="ipInput" placeholder="192.168.1.1" class="w-full">
                    <button id="scanIpButton" class="scan-button w-full mt-6">Scan IP</button>
                </div>
            </div>
        </div>

        <div id="loading" class="hidden mt-12 flex flex-col items-center text-gray-400">
            <div class="spinner mb-4"></div>
            <p>Analyzing, please wait...</p>
        </div>
        <div id="results" class="hidden mt-12 text-left p-6 rounded-2xl bg-white bg-opacity-10 w-full max-w-4xl space-y-4">
            </div>
        
        <div id="action-section" class="hidden mt-12 w-full max-w-6xl">
            <h2 class="text-3xl font-bold mb-4 text-white text-center">Take Action Against Malicious Apps</h2>
            <p class="text-lg text-gray-400 text-center mb-8">Help make the community safer by reporting suspicious apps or blocking them.</p>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-center text-center">
                    <div class="flex flex-col items-center mb-6">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-12 h-12 text-red-500 mb-4">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.062 3.377 1.77 3.377h13.964c1.708 0 2.636-1.877 1.77-3.377l-6.982-12.835a1.865 1.865 0 0 0-3.267 0L2.73 15.75a1.865 1.865 0 0 0 1.666 3.19h-1.666zM12 18.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z" />
                        </svg>
                        <p class="text-lg font-semibold text-white">Report Suspicious App</p>
                    </div>
                    <p class="text-gray-400 mb-6">Submit app details to warn others and improve detection.</p>
                    <button id="reportButton" class="report-button w-full">Report Now</button>
                </div>

                <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-center text-center">
                    <div class="flex flex-col items-center mb-6">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-12 h-12 text-yellow-500 mb-4">
                            <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5v-.75a4.5 4.5 0 0 0-9-1.398m.75-2.102H7.5a2.25 2.25 0 0 0-2.25 2.25V12h11.25v-3.75m1.5-1.5a.75.75 0 0 0 0-1.5h-15a.75.75 0 0 0 0 1.5H21V19.5a2.25 2.25 0 0 0 2.25-2.25V12" />
                        </svg>
                        <p class="text-lg font-semibold text-white">Block Malicious App</p>
                    </div>
                    <p class="text-gray-400 mb-6">Block known harmful apps from being installed (simulation).</p>
                    <button id="blockButton" class="block-button w-full">Block App</button>
                </div>
            </div>
        </div>
        
        <div id="messageModal" class="hidden fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50">
            <div class="bg-gray-800 p-8 rounded-xl shadow-lg text-center w-full max-w-sm">
                <h3 id="modalTitle" class="text-xl font-bold mb-2 text-white"></h3>
                <p id="modalMessage" class="text-gray-400 mb-6"></p>
                <button id="modalCloseButton" class="w-full bg-blue-600 text-white font-bold py-2 rounded-xl hover:bg-blue-700 transition-colors">Close</button>
            </div>
        </div>
        
        <div id="reportModal" class="hidden fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50">
            <div class="bg-gray-800 p-8 rounded-xl shadow-lg text-left w-full max-w-md">
                <h3 class="text-xl font-bold mb-4 text-white">Report a Suspicious App</h3>
                <form id="reportForm">
                    <div class="mb-4">
                        <label for="reportTargetInput" class="block text-gray-300 font-semibold mb-2">APK/URL/IP Address</label>
                        <input type="text" id="reportTargetInput" name="target" class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-white" placeholder="e.g., banking.apk or https://scam.org">
                    </div>
                    <div class="mb-4">
                        <label for="reportCategoryInput" class="block text-gray-300 font-semibold mb-2">Reason for Report</label>
                        <select id="reportCategoryInput" name="category" class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-white">
                            <option value="Phishing Site">Phishing Site</option>
                            <option value="Malware/Virus">Malware/Virus</option>
                            <option value="Spam/Fraud">Spam/Fraud</option>
                            <option value="Unusual Permissions">Unusual Permissions</option>
                            <option value="Other">Other (Please describe below)</option>
                        </select>
                    </div>
                    <div class="mb-6">
                        <label for="reportDetailsInput" class="block text-gray-300 font-semibold mb-2">Additional Details</label>
                        <textarea id="reportDetailsInput" name="details" rows="4" class="w-full bg-gray-700 border border-gray-600 rounded-md p-2 text-white" placeholder="Provide more details here..."></textarea>
                    </div>
                    <div class="flex justify-end space-x-4">
                        <button type="button" id="cancelReportButton" class="px-4 py-2 text-gray-400 font-bold rounded-xl hover:bg-gray-700 transition-colors">Cancel</button>
                        <button type="submit" id="submitReportButton" class="px-4 py-2 bg-red-600 text-white font-bold rounded-xl hover:bg-red-700 transition-colors">Submit Report</button>
                    </div>
                </form>
            </div>
        </div>

    <script>
        document.addEventListener('DOMContentLoaded', () => {
            const scanFileButton = document.getElementById('scanFileButton');
            const scanUrlButton = document.getElementById('scanUrlButton');
            const scanIpButton = document.getElementById('scanIpButton');
            const apkFile = document.getElementById('apkFile');
            const urlInput = document.getElementById('urlInput');
            const ipInput = document.getElementById('ipInput');
            const loadingSpinner = document.getElementById('loading');
            const resultsDiv = document.getElementById('results');
            const actionSection = document.getElementById('action-section');
            const messageModal = document.getElementById('messageModal');
            const modalTitle = document.getElementById('modalTitle');
            const modalMessage = document.getElementById('modalMessage');
            const modalCloseButton = document.getElementById('modalCloseButton');
            const reportButton = document.getElementById('reportButton');
            const blockButton = document.getElementById('blockButton');
            const reportModal = document.getElementById('reportModal');
            const reportForm = document.getElementById('reportForm');
            const cancelReportButton = document.getElementById('cancelReportButton');
            const reportButtonTop = document.getElementById('reportButtonTop');

            function showModal(title, message) {
                modalTitle.textContent = title;
                modalMessage.textContent = message;
                messageModal.classList.remove('hidden');
            }

            modalCloseButton.addEventListener('click', () => {
                messageModal.classList.add('hidden');
            });
            
            // Event listener for the top right report button
            reportButtonTop.addEventListener('click', (e) => {
                e.preventDefault();
                reportModal.classList.remove('hidden');
            });

            // Event listener for the report button in the action section
            if (reportButton) {
                reportButton.addEventListener('click', (e) => {
                    e.preventDefault();
                    reportModal.classList.remove('hidden');
                });
            }
            
            cancelReportButton.addEventListener('click', () => {
                reportModal.classList.add('hidden');
                reportForm.reset();
            });

            blockButton.addEventListener('click', (e) => {
                e.preventDefault();
                showModal('App Blocked (Simulated)', 'The app has been prevented from running. This is a simulation for demonstration purposes.');
            });

            reportForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                reportModal.classList.add('hidden');
                showModal('Submitting Report...', 'Your report is being sent.');
                
                const target = document.getElementById('reportTargetInput').value;
                const category = document.getElementById('reportCategoryInput').value;
                const details = document.getElementById('reportDetailsInput').value;

                try {
                    const response = await fetch('http://127.0.0.1:5000/submit_report', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ target, category, details })
                    });

                    const result = await response.json();
                    if (response.ok) {
                        showModal('Report Submitted', result.message);
                        reportForm.reset();
                    } else {
                        showModal('Submission Failed', result.error);
                    }
                } catch (error) {
                    showModal('Submission Failed', 'An error occurred. Please check the server connection.');
                }
            });

            async function handleScan(endpoint, payload, displayFunction) {
                loadingSpinner.classList.remove('hidden');
                resultsDiv.classList.add('hidden');
                actionSection.classList.add('hidden');

                try {
                    const response = await fetch(`http://127.0.0.1:5000/${endpoint}`, {
                        method: 'POST',
                        body: payload instanceof FormData ? payload : JSON.stringify(payload),
                        headers: payload instanceof FormData ? {} : { 'Content-Type': 'application/json' }
                    });

                    if (!response.ok) {
                        let errorText = 'Something went wrong on the server.';
                        try {
                            const errorData = await response.json();
                            if (errorData && errorData.error) errorText = errorData.error;
                        } catch (_) {}
                        throw new Error(errorText);
                    }

                    const result = await response.json();
                    displayFunction(result); // Use the provided display function

                } catch (error) {
                    showModal('Scan Error', error.message);
                    console.error('Error during scan:', error);
                } finally {
                    loadingSpinner.classList.add('hidden');
                }
            }
            
            function displayResults(data) {
                const isMalicious = data.classification === 'Malicious';
                const appDetails = `
                    <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-start transition-transform transform hover:scale-105">
                        <div class="flex items-center mb-4">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6 text-gray-400 mr-2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 10.5v-.75a4.5 4.5 0 0 0-9-1.398m.75-2.102H7.5a2.25 2.25 0 0 0-2.25 2.25V12h11.25v-3.75m1.5-1.5a.75.75 0 0 0 0-1.5h-15a.75.75 0 0 0 0 1.5H21V19.5a2.25 2.25 0 0 0 2.25-2.25V12" />
                            </svg>
                            <p class="text-lg font-semibold text-white">App Details</p>
                        </div>
                        <p class="text-sm text-gray-300">App Name: <span class="text-white">${data.app_name || 'N/A'}</span></p>
                        <p class="text-sm text-gray-300">Package ID: <span class="text-white">${data.package_id || 'N/A'}</span></p>
                        <p class="text-sm text-gray-300">Version: <span class="text-white">${data.version || 'N/A'}</span></p>
                        <p class="text-sm text-gray-300">Scanned On: <span class="text-white">${data.scanned_on || 'N/A'}</span></p>
                    </div>
                `;

                const permissions = `
                    <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-start transition-transform transform hover:scale-105">
                        <div class="flex items-center mb-4">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6 text-yellow-500 mr-2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.062 3.377 1.77 3.377h13.964c1.708 0 2.636-1.877 1.77-3.377l-6.982-12.835a1.865 1.865 0 0 0-3.267 0L2.73 15.75a1.865 1.865 0 0 0 1.666 3.19h-1.666zM12 18.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z" />
                            </svg>
                            <p class="text-lg font-semibold text-white">Permissions Requested</p>
                        </div>
                        <ul class="list-none space-y-2 text-sm">
                            ${(data.features_extracted?.permissions || []).map(perm => {
                                const isSafe = !['SMS', 'CONTACTS', 'BANK'].some(keyword => perm.toUpperCase().includes(keyword));
                                return `<li class="flex items-center text-gray-300">
                                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 mr-2 ${isSafe ? 'text-green-500' : 'text-red-500'}">
                                                <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
                                            </svg>
                                            ${perm}
                                        </li>`;
                            }).join('')}
                        </ul>
                    </div>
                `;

                const riskLevel = `
                    <div class="card p-8 rounded-2xl shadow-xl flex flex-col items-center text-center transition-transform transform hover:scale-105">
                        <div class="flex items-center mb-4">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-6 h-6 text-yellow-500 mr-2">
                                <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.062 3.377 1.77 3.377h13.964c1.708 0 2.636-1.877 1.77-3.377l-6.982-12.835a1.865 1.865 0 0 0-3.267 0L2.73 15.75a1.865 1.865 0 0 0 1.666 3.19h-1.666zM12 18.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5z" />
                            </svg>
                            <p class="text-lg font-semibold text-white">Risk Level</p>
                        </div>
                        <div class="rounded-lg p-2 ${isMalicious ? 'bg-red-600' : 'bg-green-600'} text-white font-bold mb-4">
                            ${isMalicious ? 'High Risk' : 'Low Risk'}
                        </div>
                        <p class="text-gray-400">${isMalicious ? 'This app may attempt to steal sensitive financial data.' : 'This app appears to be safe.'}</p>
                    </div>
                `;

                resultsDiv.innerHTML = `
                    <div class="text-center mb-8">
                        <h2 class="text-3xl font-bold mb-2 text-white">APK Scan Summary</h2>
                        <p class="text-lg text-gray-400">Here's a detailed report of the analyzed APK.</p>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-8">
                        ${appDetails}
                        ${permissions}
                        ${riskLevel}
                    </div>
                `;
                resultsDiv.classList.remove('hidden');

                if (isMalicious) {
                    actionSection.classList.remove('hidden');
                } else {
                    actionSection.classList.add('hidden');
                }
            }

            function displayUrlResults(data) {
                const isMalicious = data.classification === 'Malicious';
                resultsDiv.innerHTML = `
                    <div class="text-center mb-8">
                        <h2 class="text-3xl font-bold mb-2 text-white">URL Analysis</h2>
                    </div>
                    <div class="card p-8 rounded-2xl shadow-xl space-y-4">
                        <p class="text-sm text-gray-300">Target URL: <span class="text-white">${data.target}</span></p>
                        <p class="text-sm text-gray-300">Classification: <span class="font-bold ${isMalicious ? 'text-red-500' : 'text-green-500'}">${isMalicious ? 'Malicious' : 'Safe'}</span></p>
                        <p class="text-sm text-gray-300">Confidence Score: <span class="text-white">${(data.confidence_score * 100).toFixed(0)}%</span></p>
                        <h4 class="text-lg font-semibold text-white mt-4">Details:</h4>
                        <ul class="list-disc list-inside text-gray-400">
                            ${data.details.map(d => `<li>${d}</li>`).join('')}
                        </ul>
                    </div>
                `;
                resultsDiv.classList.remove('hidden');
                actionSection.classList.add('hidden'); // Hide the action buttons
            }
            
            function displayIpResults(data) {
                const isMalicious = data.classification === 'Malicious';
                resultsDiv.innerHTML = `
                    <div class="text-center mb-8">
                        <h2 class="text-3xl font-bold mb-2 text-white">IP Address Analysis</h2>
                    </div>
                    <div class="card p-8 rounded-2xl shadow-xl space-y-4">
                        <p class="text-sm text-gray-300">Target IP: <span class="text-white">${data.target}</span></p>
                        <p class="text-sm text-gray-300">Classification: <span class="font-bold ${isMalicious ? 'text-red-500' : 'text-green-500'}">${isMalicious ? 'Malicious' : 'Safe'}</span></p>
                        <p class="text-sm text-gray-300">Confidence Score: <span class="text-white">${(data.confidence_score * 100).toFixed(0)}%</span></p>
                        <h4 class="text-lg font-semibold text-white mt-4">Details:</h4>
                        <ul class="list-disc list-inside text-gray-400">
                            ${data.details.map(d => `<li>${d}</li>`).join('')}
                        </ul>
                    </div>
                `;
                resultsDiv.classList.remove('hidden');
                actionSection.classList.add('hidden'); // Hide the action buttons
            }

            scanFileButton.addEventListener('click', () => {
                const file = apkFile.files[0];
                if (!file) {
                    showModal('No File Selected', 'Please select an APK file to analyze.');
                    return;
                }
                const formData = new FormData();
                formData.append('apk_file', file);
                handleScan('analyze_apk', formData, displayResults);
            });

            scanUrlButton.addEventListener('click', () => {
                const url = urlInput.value.trim();
                if (!url) {
                    showModal('No URL Entered', 'Please enter a valid URL to analyze.');
                    return;
                }
                handleScan('analyze_url', { url: url }, displayUrlResults);
            });

            scanIpButton.addEventListener('click', () => {
                const ip = ipInput.value.trim();
                if (!ip) {
                    showModal('No IP Address Entered', 'Please enter a valid IP address to analyze.');
                    return;
                }
                handleScan('analyze_ip', { ip_address: ip }, displayIpResults);
            });
        });
    </script>
    </body>
    </html>
    """

@app.route('/image_d8fefc.jpg')
def serve_image():
    try:
        return send_file('image_d8fefc.jpg', mimetype='image/jpeg')
    except FileNotFoundError:
        return "Image not found", 404

@app.route('/analyze_url', methods=['POST'])
def analyze_url():
    """Endpoint for URL analysis."""
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    result = perform_url_lookup(url)

    return jsonify({
        "target": url,
        "classification": "Malicious" if result['is_malicious'] else "Safe",
        "confidence_score": 0.95 if result['is_malicious'] else 0.85,
        "details": result['details'],
        "features_extracted": {}
    })

@app.route('/analyze_apk', methods=['POST'])
def analyze_apk_file():
    """
    API endpoint to receive and analyze an uploaded APK file.
    """
    if 'apk_file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['apk_file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        temp_dir = 'temp_apks'
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)

        file_path = os.path.join(temp_dir, file.filename)
        file.save(file_path)

        try:
            features, is_malicious = extract_features(file_path)
            classification_result = classify_apk(features, is_malicious)
        finally:
            try:
                os.remove(file_path)
            except Exception:
                pass

        response = {
            "target": file.filename,
            "classification": "Malicious" if is_malicious else "Safe",
            "confidence_score": classification_result['classification_score'],
            "details": classification_result['details'],
            "features_extracted": features,
            "app_name": features.get('app_name'),
            "package_id": features.get('package_id'),
            "version": features.get('version'),
            "scanned_on": features.get('scanned_on')
        }

        return jsonify(response), 200

@app.route('/analyze_ip', methods=['POST'])
def analyze_ip():
    """Endpoint for IP address analysis."""
    data = request.json
    ip_address = data.get('ip_address')
    if not ip_address:
        return jsonify({"error": "No IP address provided"}), 400

    result = perform_ip_lookup(ip_address)

    return jsonify({
        "target": ip_address,
        "classification": "Malicious" if result['is_malicious'] else "Safe",
        "confidence_score": 0.90 if result['is_malicious'] else 0.70,
        "details": result['details'],
        "features_extracted": {}
    })

@app.route('/submit_report', methods=['POST'])
def submit_report():
    """Endpoint to handle user reports of suspicious apps/URLs."""
    data = request.json
    report_target = data.get('target')
    report_category = data.get('category')
    report_details = data.get('details')

    if not report_target or not report_category:
        return jsonify({"error": "Missing target or category"}), 400

    if report_category == "Other" and not report_details:
        return jsonify({"error": "Please provide details for 'Other' category"}), 400

    try:
        with open("reports.txt", "a") as f:
            f.write(f"Timestamp: {time.ctime()}\n")
            f.write(f"Target: {report_target}\n")
            f.write(f"Category: {report_category}\n")
            if report_details:
                f.write(f"Details: {report_details}\n")
            f.write("-" * 20 + "\n")
        return jsonify({"message": "Report submitted successfully. Thank you for your contribution!"}), 200
    except Exception as e:
        return jsonify({"error": f"An error occurred while saving the report: {e}"}), 500


if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        print("Opening web browser...")
        webbrowser.open_new("http://127.0.0.1:5000")
        time.sleep(1)

    app.run(debug=True, host='0.0.0.0', port=5000)