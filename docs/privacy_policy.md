# PRIVACY POLICY

**Voxel Estate — Automated Motivated Seller Intelligence**

**Last Updated:** September 16, 2026

---

## 1. OVERVIEW

Voxel Estate ("we", "us", "our") provides an automated real estate lead processing service. This Privacy Policy explains how we collect, use, store, and protect your data.

We are committed to protecting your privacy and handling your data transparently.

---

## 2. DATA WE COLLECT

### From Clients (Business Owners)

When you sign up for our service, we collect:

- **Account Information:** Name, company name, email address, county of interest

- **Billing Information:** Payment confirmation (via Payoneer / nsave)

- **Google Sheet ID:** The destination sheet ID for daily lead delivery

### From Client-Provided Data

When you provide us with property lead files, we process:

- **Property Information:** Address, county, listing price, price history

- **Owner Information:** Name, mailing address, phone number

- **Signals:** FSBO status, price drop flags

### Automatic Collection

We do **NOT** collect:

- Cookies or tracking data (we have no client-facing website with login)

- Location data

- Browser fingerprinting

- Any behavioral analytics

---

## 3. HOW WE USE YOUR DATA

We use your data **only** to deliver the service you paid for:

1. **Process property leads** through our Python pipeline

2. **Classify seller motivation** using AI (Google Gemini)

3. **Detect absentee owners** by comparing property and mailing addresses

4. **Deliver cleaned records** to your Google Sheet via API

5. **Log pipeline activity** for debugging and error handling

**We NEVER:**

- Sell your data to third parties

- Rent or share your data with marketing companies

- Use your data for training AI models

- Access your data outside the scope of our service

---

## 4. THIRD-PARTY SERVICES

We use the following third-party services to operate:

### Google Gemini API (Google LLC)

- **Purpose:** AI-based motivation classification

- **Data Shared:** Property lead details (addresses, prices, owner status)

- **Privacy Policy:** [policies.google.com/privacy](https://policies.google.com/privacy)

### Google Sheets API (Google LLC)

- **Purpose:** Data delivery to your Google Sheet

- **Data Shared:** Only the final processed output

- **Access:** Service Account with limited Editor permissions

### Payoneer / nsave

- **Purpose:** Payment processing

- **Data Shared:** Payment amount, your email

- **Privacy Policy:** [payoneer.com/privacy](https://www.payoneer.com/privacy/)

**All third-party providers are bound by their own privacy policies.**

---

## 5. DATA STORAGE AND SECURITY

### Where Data is Stored

- **Processing:** On our secure server (VPS)

- **API Keys:** Stored in encrypted `.env` files (never committed to code)

- **Client Configs:** Stored in git-ignored folders

- **Logs:** Retained for 30 days, then auto-deleted

### Security Measures

- SSL/TLS encryption for all API calls

- Service Account authentication (not passwords)

- `.gitignore` protection against accidental leaks

- No public exposure of client data

- Regular security reviews of the pipeline

### What is NOT Stored

- We do **NOT** keep a copy of your raw CSV files after processing

- We do **NOT** store your payment credentials (handled by Payoneer)

- We do **NOT** store your Google account password

---

## 6. DATA RETENTION

| Data Type | Retention Period |

|-----------|------------------|

| Client account info | Duration of service + 30 days |

| Raw CSV files | Deleted immediately after processing |

| Processed leads | Only in your Google Sheet |

| Activity logs | 30 days, then auto-deleted |

| Error logs | 30 days, then auto-deleted |

| Billing records | 7 years (tax compliance) |

**Upon cancellation, all data is deleted within 30 days.**

---

## 7. YOUR RIGHTS

You have the right to:

- **Access** your data — request a summary at any time

- **Correct** your data — update account information

- **Delete** your data — request deletion upon cancellation

- **Export** your data — download all leads from your Google Sheet

- **Withdraw Consent** — cancel service at any time

**To exercise these rights, email:** [realestateagent276@gmail.com](mailto:realestateagent276@gmail.com)

**Response time:** Within 7 business days.

---

## 8. CHILDREN'S PRIVACY

Our service is for business use only (B2B). We do not knowingly collect data from anyone under 18.

If you believe we have collected data from a minor, contact us immediately.

---

## 9. INTERNATIONAL DATA TRANSFERS

We operate from Bangladesh and serve clients in the United States.

- Data may be transferred between countries (US ↔ Bangladesh) for processing.

- All transfers use encrypted connections.

- We comply with reasonable international data protection standards.

---

## 10. COOKIES AND TRACKING

We do **NOT** use:

- Cookies

- Web beacons

- Pixels

- Third-party analytics

The only tracking we do is internal activity logging for service reliability.

---

## 11. CHANGES TO THIS POLICY

We may update this Privacy Policy occasionally. Changes will be:

- Posted on our website ([voxelestate.netlify.app](http://voxelestate.netlify.app))

- Emailed to active clients

- Effective 14 days after notification

**Continued use of our service means you accept the updated policy.**

---

## 12. CONTACT US

For questions, concerns, or data requests:

**Email:** [realestateagent276@gmail.com](mailto:realestateagent276@gmail.com)

**Website:** [voxelestate.netlify.app](http://voxelestate.netlify.app)

**Mailing Address:** Available on request

---

## 13. COMPLIANCE

We aim to comply with:

- **CCPA** (California Consumer Privacy Act) — for CA residents

- **GDPR principles** — where applicable

- **FTC guidelines** — for US business practices

If you have a compliance concern, contact us first. We'll respond within 7 days.

---

*Voxel Estate — Automated Motivated Seller Intelligence*

*Max 3 investors per US county — County exclusive.*