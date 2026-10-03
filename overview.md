# Intelligent Pharmacy Management System — Project Rules

## 1. Project Identity

You are assisting with the development of a final-year academic software project titled:

**Intelligent Pharmacy Management and Explainable Clinical Decision Support System**

The application is designed primarily for **independent and community pharmacies in Sierra Leone**, not hospital pharmacies.

Always preserve this context when designing, generating, modifying, or reviewing the application.

---

## 2. Core Product Purpose

The system is a web-based pharmacy management platform that combines:

* Medicine management
* Medicine batch management
* Inventory management
* Direct medicine sales
* External prescription dispensing
* Consultation-based dispensing
* Transaction history
* Stock and expiry alerts
* Basic reporting
* Explainable Clinical Decision Support

The system should improve pharmacy operations without unnecessarily complicating normal medicine dispensing.

---

## 3. Primary Users

There are two primary system roles:

### Administrator

The Administrator can:

* Manage users
* Manage medicines
* Manage medicine categories
* Manage inventory
* Add medicine batches
* Adjust stock
* View transactions
* View alerts
* Generate reports
* View dashboard information
* Access appropriate administrative settings

### Pharmacist / Pharmacy Staff

There is NO separate Prescriber role.

In independent pharmacies in the target environment, pharmacy workers may perform both medicine recommendation and dispensing activities.

Pharmacy Staff can:

* Search medicines
* View stock
* Perform Direct Sales
* Process External Prescriptions
* Record Consultations
* Select medicines
* Enter dosage information when appropriate
* Run clinical safety checks
* Review explainable alerts
* Dispense medicine
* View transaction history

---

## 4. Three Core Dispensing Workflows

Every dispensing transaction must belong to one of these three types:

1. `DIRECT_SALE`
2. `EXTERNAL_PRESCRIPTION`
3. `CONSULTATION`

Do not introduce additional primary transaction types unless explicitly requested.

---

## 5. Direct Sale Rules

Direct Sale is a major and common workflow.

A customer may enter the pharmacy already knowing what medicine they want.

Example:

> Customer requests two strips of Paracetamol.

The system must allow:

`Select Direct Sale → Search Medicine → Add Quantity → Check Stock → Applicable Safety Checks → Confirm Dispensing → Update Inventory → Save Transaction`

For Direct Sale:

* DO NOT require patient registration.
* DO NOT require patient name.
* DO NOT require symptoms.
* DO NOT require diagnosis.
* DO NOT require a prescription.
* DO NOT force a consultation.
* Allow multiple medicines in one transaction.

Keep this workflow fast and simple.

---

## 6. External Prescription Rules

External Prescription is used when a customer brings a prescription issued elsewhere.

Allow Pharmacy Staff to enter:

* Medicine
* Strength
* Dose
* Frequency
* Duration
* Quantity

Patient registration must remain optional.

The system should perform only the clinical checks supported by the available information.

Do not attempt to reproduce or independently replace the diagnosis from the external healthcare provider.

---

## 7. Consultation Rules

Consultation is used when a customer explains symptoms and Pharmacy Staff assess the complaint.

Optional consultation information may include:

* Age
* Sex where clinically relevant
* Symptoms
* Symptom duration
* Current medicines
* Known allergies
* Weight where required
* Pregnancy/breastfeeding status where clinically relevant
* Notes

Full patient identity is not mandatory.

The pharmacist or pharmacy worker chooses the medicine.

The application must NOT independently make a definitive medical diagnosis.

---

## 8. Patient Data Principle

The initial system does NOT maintain mandatory permanent patient profiles.

Do not create dependencies requiring every dispensing transaction to have a Patient record.

Temporary clinical information should be associated with a Consultation or dispensing transaction when necessary.

Direct Sales must work without patient information.

---

## 9. Central Transaction Model

`DispensingTransaction` is the central business transaction.

A transaction should contain:

* Unique transaction ID
* Transaction type
* Responsible staff/user
* Date and time
* Status
* Transaction items
* Total amount
* Applicable clinical alerts

A transaction can contain multiple `DispensingItem` records.

Each Dispensing Item should reference the relevant Medicine and, where appropriate, the Medicine Batch used.

---

## 10. Inventory Rules

Medicine and Medicine Batch are separate concepts.

### Medicine

Stores general product information such as:

* Generic name
* Brand name
* Category
* Dosage form
* Strength
* Unit
* Minimum stock level
* Status

### Medicine Batch

Stores batch-specific information such as:

* Batch number
* Quantity received
* Quantity remaining
* Cost price
* Selling price
* Date received
* Expiry date

Do NOT store a single expiry date directly on Medicine when multiple batches can exist.

---

## 11. Stock Business Rules

Always enforce these rules:

1. Dispensed quantity must not exceed available valid stock.
2. Expired batches must not count as available dispensing stock.
3. Inventory must decrease only after dispensing is successfully confirmed.
4. Cancelled or failed transactions must not reduce inventory.
5. Stock adjustments must be recorded.
6. Important stock changes should record the responsible user.
7. Low stock should be detected using configured minimum stock levels.
8. Medicine expiry should be evaluated at batch level.
9. Inventory and transaction updates should occur atomically whenever possible.

Never allow a completed transaction to be saved while its required inventory update silently fails.

---

## 12. Clinical Decision Support Purpose

The Clinical Decision Support System is a **support tool**, not an autonomous prescriber.

It initially supports:

1. Drug–drug interaction checking
2. Dosage checking
3. Allergy conflict checking

Clinical rules should come from a structured, verifiable clinical knowledge base.

Do NOT rely on a generative language model as the primary source of medication safety decisions.

---

## 13. Explainable AI Architecture

Use a transparent architecture:

`Transaction/Consultation Data`
→ `Clinical Rules Engine`
→ `Applicable Safety Checks`
→ `Clinical Findings`
→ `Interpretable Risk Assessment where implemented`
→ `Explanation`
→ `Pharmacist Review`

The deterministic clinical rules engine should remain authoritative for configured interaction, allergy, and dosage rules.

If an interpretable ML model such as a Decision Tree is introduced, use it for secondary risk classification or analysis.

Do NOT allow an ML model to silently override deterministic clinical safety rules.

---

## 14. Drug Interaction Rules

Use a structured `DrugInteractionRule` model containing information such as:

* medicine_a
* medicine_b
* severity
* interaction_description
* explanation
* recommendation
* source_reference
* active status

When multiple medicines exist in one transaction, check relevant medicine combinations.

When an interaction is found, return a structured finding.

Example structure:

* Alert Type: Drug Interaction
* Medicines Involved
* Severity
* Reason
* Explanation
* Recommendation
* Clinical Source

---

## 15. Dosage Rules

Use structured dosage rules.

Possible fields include:

* Medicine
* Age range/group
* Weight criteria where appropriate
* Minimum dose
* Maximum dose
* Frequency
* Source/reference

Only perform dosage validation when sufficient required information exists.

Never invent missing patient information.

---

## 16. Allergy Rules

Where allergy information is available:

* Compare recorded allergies against selected medicines or configured medicine classes.
* Generate an explainable warning when a configured conflict exists.

If allergy information is unavailable, do NOT report:

`Allergy Check: Passed`

Instead report:

`Not Checked — Allergy information unavailable`

---

## 17. Clinical Check Status

Each clinical check must return an explicit status.

Use:

* `PASSED`
* `WARNING`
* `NOT_APPLICABLE`
* `NOT_CHECKED`

`NOT_CHECKED` should include the reason.

Example:

`Dosage Check: NOT_CHECKED — patient age/weight required by this rule was not provided.`

Never present an unavailable or incomplete clinical check as successfully passed.

---

## 18. Explainability Rules

Every clinical warning must explain:

* What was detected
* Which medicine(s) caused it
* Severity
* Why the rule triggered
* Recommended review/action
* Source/reference where available

Avoid unexplained messages such as:

* "AI says unsafe"
* "Dangerous medicine"
* "AI rejected prescription"
* "Invalid drug"

The user must understand why the system generated the warning.

---

## 19. Clinical Decision Authority

The system does not replace pharmacist judgment.

Clinical warnings should normally require review rather than automatically presenting themselves as final medical decisions.

Do not describe the system as independently diagnosing patients.

Prefer terminology such as:

* Clinical Decision Support
* Safety Check
* Clinical Warning
* Medication Risk
* Recommendation for Review

---

## 20. Core Database Entities

Maintain consistency with these primary entities unless requirements explicitly change:

* Role
* User
* MedicineCategory
* Medicine
* MedicineBatch
* StockTransaction
* DispensingTransaction
* DispensingItem
* Consultation
* ClinicalAlert
* DrugInteractionRule
* DosageRule
* AllergyRule
* AuditLog

Do not casually duplicate concepts already represented by these entities.

---

## 21. Key Relationships

Preserve these relationships:

* One Role → many Users
* One MedicineCategory → many Medicines
* One Medicine → many MedicineBatches
* One MedicineBatch → many StockTransactions
* One User → many DispensingTransactions
* One DispensingTransaction → many DispensingItems
* One Medicine → many DispensingItems
* One DispensingTransaction → zero or one Consultation
* One DispensingTransaction → zero or many ClinicalAlerts
* One User → many AuditLogs

---

## 22. Application Architecture

Use a layered web architecture.

### Presentation Layer

User interface displayed through the browser.

### Application Layer

Contains:

* Authentication
* Authorization
* Medicine logic
* Inventory logic
* Dispensing logic
* Clinical decision-support logic
* Reporting logic
* Validation
* Business rules

### Data Layer

Stores application and clinical knowledge-base data.

Do not place important business logic directly inside UI components/templates.

---

## 23. Technology Stack

Default stack unless explicitly changed:

### Backend

Python with Django.

Prefer Django for:

* ORM
* Authentication
* Authorization
* Database models
* Forms/validation
* Admin functionality
* Structured application architecture

### Database

MySQL

### Frontend

* HTML5
* CSS3
* JavaScript

Use additional frontend libraries only when they clearly improve the project and do not unnecessarily increase complexity.

### Development

* Git
* VS Code / Antigravity

---

## 24. Django Development Conventions

When using Django:

* Use Django ORM rather than raw SQL unless raw SQL is justified.
* Keep models focused on persistent domain data.
* Use services/helpers for complex business logic.
* Use forms or serializers for validation.
* Use Django authentication securely.
* Use permission checks for protected actions.
* Use database transactions for operations that update both dispensing records and inventory.
* Avoid giant views containing unrelated business logic.
* Prefer modular Django apps where appropriate.

Possible application modules include:

* accounts
* medicines
* inventory
* dispensing
* clinical
* reports

Avoid unnecessary over-engineering for the academic MVP.

---

## 25. Code Quality Rules

Generate code that is:

* Modular
* Readable
* Maintainable
* Appropriately documented
* PEP 8 compliant for Python
* Consistently named
* Easy for a student development team to understand

Prefer straightforward solutions over clever abstractions.

Before changing existing code:

1. Inspect relevant files.
2. Understand existing architecture.
3. Preserve working functionality.
4. Make the smallest coherent change.
5. Update related tests where appropriate.

Do not rewrite unrelated files unnecessarily.

---

## 26. Security Rules

Always:

* Hash passwords using Django-supported password mechanisms.
* Never store plain-text passwords.
* Validate user input.
* Require authentication for protected operations.
* Enforce role permissions server-side.
* Protect sensitive clinical/transaction data.
* Avoid leaking secrets in source code.
* Store credentials and secrets in environment variables.
* Do not commit `.env` files or secrets.

---

## 27. Auditability

Important activities should be traceable.

Examples:

* User created
* User disabled
* Medicine created/edited
* Stock received
* Stock adjusted
* Medicine dispensed
* Transaction completed

Audit information should include:

* User
* Action
* Relevant entity
* Timestamp
* Description where useful

---

## 28. Dashboard and Reporting

Dashboard information should be derived from real stored data.

Potential metrics:

* Total medicines
* Low-stock medicines
* Out-of-stock medicines
* Expiring medicines
* Expired batches
* Today's transactions
* Today's sales value
* Recent clinical warnings

Do not hardcode dashboard statistics.

Initial reports include:

* Inventory Report
* Low Stock Report
* Expiry Report
* Dispensing Report
* Clinical Alert Report

---

## 29. MVP Priority

Prioritize development in this order:

1. Project/database foundation
2. Authentication and roles
3. Medicine management
4. Medicine batches
5. Inventory management
6. Direct Sale
7. Automatic inventory deduction
8. Transaction history
9. External Prescription
10. Consultation
11. Drug Interaction Engine
12. Explainable alerts
13. Allergy checking
14. Dosage checking
15. Dashboard
16. Reports
17. Testing and evaluation

Do not prioritize advanced features before the basic pharmacy transaction workflow is reliable.

---

## 30. First Core Milestone

The first complete vertical slice should allow:

`Login → Add Medicine → Add Medicine Batch/Stock → Direct Sale → Confirm Dispensing → Automatically Reduce Stock → Save Transaction`

Ensure this workflow works correctly before introducing complex AI functionality.

---

## 31. Out of Scope for MVP

Do not implement unless explicitly requested:

* Insurance processing
* Online payments
* Autonomous diagnosis
* Autonomous prescribing
* Full Electronic Health Records
* Multi-branch pharmacy architecture
* Advanced supply-chain management
* Barcode scanning
* SMS integration
* Mobile apps
* Advanced demand forecasting
* Fully offline synchronization
* Large language models as medical decision-makers

---

## 32. Design Principle

Follow this principle throughout development:

**Do not make a simple pharmacy transaction unnecessarily complicated.**

Direct Sale should remain fast.

Only request clinical information when it is relevant to the transaction or safety check.

Build for the actual operational environment of independent/community pharmacies in Sierra Leone.

---

## 33. When Requirements Are Unclear

Do not invent major product requirements.

First inspect:

* Existing code
* Project documentation
* Database models
* Current workflow
* This rule file

For minor technical implementation details, choose the simplest approach consistent with the architecture.

For major changes affecting workflow, data model, clinical behavior, or project scope, clearly identify the assumption before implementing it.

---

## 34. Definition of Done

A feature is not complete merely because the UI exists.

A feature should:

* Work through the backend
* Persist correct data
* Enforce permissions
* Validate input
* Handle expected failure cases
* Preserve inventory consistency where relevant
* Display appropriate feedback
* Follow project business rules
* Be reasonably testable

For clinical functionality, it must additionally provide transparent and explainable results.
