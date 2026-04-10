#!/usr/bin/env python3
"""
Patch taskData in career tsx files using current task table (no MIN_TASK_N threshold).
Only updates the taskData array — leaves all other content untouched.
"""

import csv
import re
import sys
from pathlib import Path

TASK_TABLE  = "data/intermediate/onet_economic_index_task_table.csv"
CAREERS_DIR = Path("../ai-resilient-occupations-site/src/data/careers")
TOP_N_TASKS = 10

# Curated short labels keyed by full task text
SHORT_LABELS = {
    # air-traffic-controller
    "Transfer control of departing flights to traffic control centers and accept control of arriving flights.": "Transfer flight control",
    "Inform pilots about nearby planes or potentially hazardous conditions, such as weather, speed and direction of wind, or visibility problems.": "Advise pilots on hazards",
    "Monitor or direct the movement of aircraft within an assigned air space or on the ground at airports to minimize delays and maximize safety.": "Direct aircraft movement",
    "Monitor aircraft within a specific airspace, using radar, computer equipment, or visual references.": "Monitor airspace via radar",
    "Direct ground traffic, including taxiing aircraft, maintenance or baggage vehicles, or airport workers.": "Direct ground traffic",
    "Issue landing and take-off authorizations or instructions.": "Issue landing/takeoff clearances",
    "Direct pilots to runways when space is available or direct them to maintain a traffic pattern until there is space for them to land.": "Direct pilots to runways",
    "Contact pilots by radio to provide meteorological, navigational, or other information.": "Contact pilots by radio",
    "Maintain radio or telephone contact with adjacent control towers, terminal control units, or other area control centers to coordinate aircraft movement.": "Coordinate with adjacent centers",
    "Determine the timing or procedures for flight vector changes.": "Determine flight vector changes",
    # computer-information-systems-manager
    "Manage backup, security and user help systems.": "Manage backup/security systems",
    "Provide users with technical support for computer problems.": "Provide technical support",
    "Assign and review the work of systems analysts, programmers, and other computer-related workers.": "Assign/review staff work",
    "Direct daily operations of department, analyzing workflow, establishing priorities, developing standards and setting deadlines.": "Direct daily operations",
    "Meet with department heads, managers, supervisors, vendors, and others, to solicit cooperation and resolve problems.": "Coordinate with stakeholders",
    "Review project plans to plan and coordinate project activity.": "Review project plans",
    "Stay abreast of advances in technology.": "Stay current on technology",
    "Prepare and review operational reports or project progress reports.": "Prepare operational reports",
    "Consult with users, management, vendors, and technicians to assess computing needs and system requirements.": "Assess computing needs",
    "Develop computer information resources, providing for data security and control, strategic computing, and disaster recovery.": "Develop IT infrastructure",
    # computer-programmer
    "Write, analyze, review, and rewrite programs, using workflow chart and diagram, and applying knowledge of computer capabilities, subject matter, and symbolic logic.": "Write/analyze/rewrite programs",
    "Correct errors by making appropriate changes and rechecking the program to ensure that the desired results are produced.": "Correct program errors",
    "Perform or direct revision, repair, or expansion of existing programs to increase operating efficiency or adapt to new requirements.": "Revise/expand programs",
    "Write, update, and maintain computer programs or software packages to handle specific jobs such as tracking inventory, storing or retrieving data, or controlling other equipment.": "Write/maintain software packages",
    "Consult with managerial, engineering, and technical personnel to clarify program intent, identify problems, and suggest changes.": "Consult with technical personnel",
    "Conduct trial runs of programs and software applications to be sure they will produce the desired information and that the instructions are correct.": "Conduct trial runs",
    "Compile and write documentation of program development and subsequent revisions, inserting comments in the coded instructions so others can understand the program.": "Write program documentation",
    "Consult with and assist computer operators or system analysts to define and resolve problems in running computer programs.": "Assist operators/analysts",
    "Perform systems analysis and programming tasks to maintain and control the use of computer systems software as a systems programmer.": "Perform systems analysis",
    "Prepare detailed workflow charts and diagrams that describe input, output, and logical operation, and convert them into a series of instructions coded in a computer language.": "Prepare workflow charts",
    # computer-science-researcher
    "Analyze problems to develop solutions involving computer hardware and software.": "Analyze problems/develop solutions",
    "Apply theoretical expertise and innovation to create or apply new technology, such as adapting principles for applying computers to new uses.": "Apply theory to new technology",
    "Assign or schedule tasks to meet work priorities and goals.": "Assign/schedule tasks",
    "Design computers and the software that runs them.": "Design hardware/software",
    "Conduct logical analyses of business, scientific, engineering, and other technical problems, formulating mathematical models of problems for solution by computers.": "Conduct technical analyses",
    "Meet with managers, vendors, and others to solicit cooperation and resolve problems.": "Resolve problems with stakeholders",
    "Maintain network hardware and software, direct network security measures, and monitor networks to ensure availability to system users.": "Maintain network security",
    "Participate in multidisciplinary projects in areas such as virtual reality, human-computer interaction, or robotics.": "Participate in research projects",
    "Evaluate project plans and proposals to assess feasibility issues.": "Evaluate project feasibility",
    "Direct daily operations of departments, coordinating project activities with other departments.": "Direct department operations",
    # computer-systems-architect
    "Communicate with staff or clients to understand specific system requirements.": "Gather system requirements",
    "Monitor system operation to detect potential problems.": "Monitor system operations",
    "Direct the analysis, development, and operation of complete computer systems.": "Direct systems development",
    "Investigate system component suitability for specified purposes, and make recommendations regarding component use.": "Evaluate system components",
    "Direct the installation of operating systems, network or application software, or computer or network hardware.": "Direct system installation",
    "Perform ongoing hardware and software maintenance operations, including installing or upgrading hardware or software.": "Perform system maintenance",
    "Provide customers or installation teams guidelines for implementing secure systems.": "Guide secure system setup",
    "Provide technical guidance or support for the development or troubleshooting of systems.": "Provide technical guidance",
    "Identify system data, hardware, or software components required to meet user needs.": "Identify system requirements",
    "Verify stability, interoperability, portability, security, or scalability of system architecture.": "Verify system architecture",
    # data-scientist
    "Analyze, manipulate, or process large sets of data using statistical software.": "Analyze/process large datasets",
    "Apply feature selection algorithms to models predicting outcomes of interest, such as sales, attrition, and healthcare use.": "Apply feature selection algorithms",
    "Apply sampling techniques to determine groups to be surveyed or use complete enumeration methods.": "Apply sampling techniques",
    "Clean and manipulate raw data using statistical software.": "Clean/manipulate raw data",
    "Compare models using statistical performance metrics, such as loss functions or proportion of explained variance.": "Compare model performance",
    "Create graphs, charts, or other visualizations to convey the results of data analysis using specialized software.": "Create data visualizations",
    "Deliver oral or written presentations of the results of mathematical modeling and data analysis to management or other end users.": "Present analysis results",
    "Design surveys, opinion polls, or other instruments to collect data.": "Design data collection instruments",
    "Identify business problems or management objectives that can be addressed through data analysis.": "Identify business problems",
    "Identify relationships and trends or any factors that could affect the results of research.": "Identify trends/relationships",
    # database-architect
    "Collaborate with system architects, software architects, design analysts, and others to understand business or industry requirements.": "Gather business requirements",
    "Develop and document database architectures.": "Document database architectures",
    "Design databases to support business applications, ensuring system scalability, security, performance, and reliability.": "Design databases for applications",
    "Work as part of a project team to coordinate database development and determine project scope and limitations.": "Coordinate database development",
    "Develop database architectural strategies at the modeling, design and implementation stages to address business or industry requirements.": "Develop architectural strategies",
    "Design database applications, such as interfaces, data transfer mechanisms, global temporary tables, data partitions, and function-based indexes to enable efficient access of the generic database structure.": "Design database applications",
    "Develop data models for applications, metadata tables, views or related database structures.": "Develop data models",
    "Develop data model describing data elements and their use, following procedures and using pen, template or computer software.": "Model data elements",
    "Develop methods for integrating different products so they work properly together, such as customizing commercial databases to fit specific needs.": "Develop integration methods",
    "Document and communicate database schemas, using accepted notations.": "Document database schemas",
    # information-security-analyst
    "Monitor current reports of computer viruses to determine when to update virus protection systems.": "Monitor virus reports",
    "Develop plans to safeguard computer files against accidental or unauthorized modification, destruction, or disclosure and to meet emergency data processing needs.": "Develop file safeguard plans",
    "Modify computer security files to incorporate new software, correct errors, or change individual access status.": "Modify security files",
    "Encrypt data transmissions and erect firewalls to conceal confidential information as it is being transmitted and to keep out tainted digital transfers.": "Encrypt data/erect firewalls",
    "Monitor use of data files and regulate access to safeguard information in computer files.": "Monitor data file access",
    "Confer with users to discuss issues such as computer data access needs, security violations, and programming changes.": "Confer with users",
    "Perform risk assessments and execute tests of data processing system to ensure functioning of data processing activities and security measures.": "Perform risk assessments",
    "Review violations of computer security procedures and discuss procedures with violators to ensure violations are not repeated.": "Review security violations",
    "Document computer security and emergency measures policies, procedures, and tests.": "Document security policies",
    "Coordinate implementation of computer system plan with establishment personnel and outside vendors.": "Coordinate system plan",
    # it-project-manager
    "Confer with project personnel to identify and resolve problems.": "Resolve project problems",
    "Schedule and facilitate meetings related to information technology projects.": "Facilitate project meetings",
    "Manage project execution to ensure adherence to budget, schedule, and scope.": "Manage project execution",
    "Direct or coordinate activities of project personnel.": "Coordinate project personnel",
    "Monitor or track project milestones and deliverables.": "Track milestones/deliverables",
    "Initiate, review, or approve modifications to project plans.": "Approve plan modifications",
    "Develop or update project plans for information technology projects including information such as project objectives, technologies, systems, information specifications, schedules, funding, and staffing.": "Develop/update project plans",
    "Assess current or future customer needs and priorities by communicating directly with customers, conducting surveys, or other methods.": "Assess customer needs",
    "Prepare project status reports by collecting, analyzing, and summarizing information and trends.": "Prepare status reports",
    "Monitor the performance of project team members, providing and documenting performance feedback.": "Monitor team performance",
    # licensed-practical-nurse
    "Supervise nurses' aides or assistants.": "Supervise nursing aides",
    "Observe patients, charting and reporting changes in patients' conditions, such as adverse reactions to medication or treatment, and taking any necessary action.": "Observe/chart patient changes",
    "Answer patients' calls and determine how to assist them.": "Respond to patient calls",
    "Measure and record patients' vital signs, such as height, weight, temperature, blood pressure, pulse, or respiration.": "Measure/record vital signs",
    "Administer prescribed medications or start intravenous fluids, noting times and amounts on patients' charts.": "Administer medications/IV fluids",
    "Provide basic patient care or treatments, such as taking temperatures or blood pressures, dressing wounds, treating bedsores, giving enemas or douches, rubbing with alcohol, massaging, or performing catheterizations.": "Provide basic patient care",
    "Evaluate nursing intervention outcomes, conferring with other healthcare team members as necessary.": "Evaluate nursing outcomes",
    "Work as part of a healthcare team to assess patient needs, plan and modify care, and implement interventions.": "Coordinate patient care",
    "Provide medical treatment or personal care to patients in private home settings, such as cooking, keeping rooms orderly, seeing that patients are comfortable and in good spirits, or instructing family members in simple nursing tasks.": "Provide in-home patient care",
    "Record food and fluid intake and output.": "Record fluid intake/output",
    # software-developer
    "Monitor functioning of equipment to ensure system operates in conformance with specifications.": "Monitor system conformance",
    "Modify existing software to correct errors, adapt it to new hardware, or upgrade interfaces and improve performance.": "Modify/upgrade existing software",
    "Analyze user needs and software requirements to determine feasibility of design within time and cost constraints.": "Analyze user/software requirements",
    "Develop or direct software system testing or validation procedures, programming, or documentation.": "Direct software testing",
    "Confer with systems analysts, engineers, programmers and others to design systems and to obtain information on project limitations and capabilities, performance requirements and interfaces.": "Confer with project team",
    "Store, retrieve, and manipulate data for analysis of system capabilities and requirements.": "Manipulate system data",
    "Supervise the work of programmers, technologists and technicians and other engineering and scientific personnel.": "Supervise programmers/technicians",
    "Design, develop and modify software systems, using scientific analysis and mathematical models to predict and measure outcomes and consequences of design.": "Design/develop software systems",
    "Prepare reports or correspondence concerning project specifications, activities, or status.": "Prepare project reports",
    "Determine system performance standards.": "Set performance standards",
    # software-qa-analyst
    "Identify, analyze, and document problems with program function, output, online screen, or content.": "Identify/document program defects",
    "Document software defects, using a bug tracking system, and report defects to software developers.": "Log defects in bug tracker",
    "Install, maintain, or use software testing programs.": "Maintain testing programs",
    "Document test procedures to ensure replicability and compliance with standards.": "Document test procedures",
    "Develop testing programs that address areas such as database impacts, software scenarios, regression testing, negative testing, error or bug retests, or usability.": "Develop testing programs",
    "Provide feedback and recommendations to developers on software usability and functionality.": "Provide developer feedback",
    "Create or maintain databases of known test defects.": "Maintain defect databases",
    "Monitor program performance to ensure efficient and problem-free operations.": "Monitor program performance",
    "Monitor bug resolution efforts and track successes.": "Track bug resolution",
    "Design test plans, scenarios, scripts, or procedures.": "Design test plans/scripts",
    # web-administrator
    "Monitor systems for intrusions or denial of service attacks, and report security breaches to appropriate personnel.": "Monitor for intrusions/attacks",
    "Determine sources of Web page or server problems, and take action to correct such problems.": "Diagnose server problems",
    "Correct testing-identified problems, or recommend actions for their resolution.": "Correct identified problems",
    "Review or update Web page content or links in a timely manner, using appropriate tools.": "Update web content/links",
    "Back up or modify applications and related data to provide for disaster recovery.": "Back up applications/data",
    "Track, compile, and analyze Web site usage data.": "Analyze site usage data",
    "Document application and Web site changes or change procedures.": "Document site changes",
    "Collaborate with Web developers to create and operate internal and external Web sites, or to manage projects, such as e-marketing campaigns.": "Collaborate with web developers",
    "Collaborate with development teams to discuss, analyze, or resolve usability issues.": "Resolve usability issues",
    "Gather, analyze, or document user feedback to locate or resolve sources of problems.": "Gather/analyze user feedback",
    # web-and-digital-interface-designer
    "Collaborate with management or users to develop e-commerce strategies and to integrate these strategies with Web sites.": "Develop e-commerce strategies",
    "Collaborate with web development professionals, such as front-end or back-end developers, to complete the full scope of Web development projects.": "Collaborate with developers",
    "Communicate with network personnel or Web site hosting agencies to address hardware or software issues affecting Web sites.": "Coordinate hosting/infrastructure",
    "Conduct user research to determine design requirements and analyze user feedback to improve design quality.": "Conduct user research",
    "Confer with management or development teams to prioritize needs, resolve conflicts, develop content criteria, or choose solutions.": "Prioritize design needs",
    "Create searchable indices for Web page content.": "Create content indices",
    "Create Web models or prototypes that include physical, interface, logical, or data models.": "Create web prototypes",
    "Design, build, or maintain Web sites, using authoring or scripting languages, content creation tools, management tools, and digital media.": "Design/build web sites",
    "Develop and document style guidelines for Web site content.": "Develop style guidelines",
    "Develop new visual design concepts and modify concepts based on stakeholder feedback.": "Develop visual design concepts",
    # software-technology
    "Write supporting code for Web applications or Web sites.": "Write supporting code",
    "Design, build, or maintain Web sites, using authoring or scripting languages, content creation tools, management tools, and digital media.": "Design/build websites",
    "Back up files from Web sites to local directories for instant recovery in case of problems.": "Back up files",
    "Evaluate code to ensure that it is valid, is properly structured, meets industry standards, and is compatible with browsers, devices, or operating systems.": "Evaluate code quality",
    "Evaluate code to ensure that it is valid, is properly structured, meets industry standards, and is compatible with browsers, devices, or operating systems.": "Evaluate code quality",
    "Respond to user email inquiries, or set up automated systems to send responses.": "Respond to email",
    "Perform or direct Web site updates.": "Perform site updates",
    "Perform Web site tests according to planned schedules, or after any Web site or product revision.": "Run site tests",
    "Confer with management or development teams to prioritize needs, resolve conflicts, develop content criteria, or choose solutions.": "Confer with dev teams",
    "Select programming languages, design tools, or applications.": "Select programming tools",
    "Maintain understanding of current Web technologies or programming practices through continuing education, reading, or participation in professional conferences, workshops, or groups.": "Maintain tech knowledge",
    # shared across roles
    "Incorporate technical considerations into Web site design plans, such as budgets, equipment, performance requirements, and legal issues including accessibility and privacy.": "Provide site specs",
    "Incorporate technical considerations into Web site design plans, such as budgets, equipment, performance requirements, or legal issues including accessibility and privacy.": "Provide site specs",
    "Identify or maintain links to and from other Web sites and check for broken links, using appropriate software.": "Maintain site links",
    "Research, document, rate, or select alternatives for Web architecture or technologies.": "Research web architecture",
    "Develop databases that support Web applications and Web sites.": "Develop databases",
    "Create and enforce database development standards.": "Enforce database standards",
    "Identify and evaluate industry trends in database systems to serve as a source of information and advice for upper management.": "Track database industry trends",
    "Plan and install upgrades of database management system software to enhance performance.": "Plan database upgrades",
    "Develop or maintain archived procedures, procedural codes, or queries for applications.": "Maintain archived procedures",
    "Develop implementation plans that include analyses such as cost-benefit or resource allocation.": "Develop implementation plans",
    "Develop or update project plans for information technology projects including information such as project objectives, technologies, systems, information specifications, schedules, funding, and staffing.": "Develop/update project plans",
}

SLUG_TO_CODE = {
    "air-traffic-controller":               "53-2021.00",
    "computer-information-systems-manager": "11-3021.00",
    "computer-programmer":                  "15-1251.00",
    "computer-science-researcher":          "15-1221.00",
    "computer-systems-architect":           "15-1299.08",
    "data-scientist":                       "15-2051.00",
    "database-architect":                   "15-1243.00",
    "information-security-analyst":         "15-1212.00",
    "it-project-manager":                   "15-1299.09",
    "licensed-practical-nurse":             "29-2061.00",
    "software-developer":                   "15-1252.00",
    "software-qa-analyst":                  "15-1253.00",
    "web-administrator":                    "15-1299.01",
    "web-and-digital-interface-designer":   "15-1255.00",
    "software-technology":                   "15-1254.00",
}

def short_label(text: str) -> str:
    return SHORT_LABELS.get(text, text)

def safe_float(val):
    try:
        return round(float(val), 1) if val not in ("", None) else None
    except (ValueError, TypeError):
        return None

def safe_int(val):
    try:
        return int(float(val)) if val not in ("", None) else None
    except (ValueError, TypeError):
        return None

def fmt(val):
    return "null" if val is None else str(val)

def load_task_table():
    table = {}
    with open(TASK_TABLE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            table.setdefault(row["onet_code"], []).append(row)
    return table

def build_task_data(task_rows):
    sorted_rows = sorted(
        task_rows,
        key=lambda r: float(r["task_weight"]) if r["task_weight"] else 0,
        reverse=True
    )[:TOP_N_TASKS]

    result = []
    for r in sorted_rows:
        n = safe_int(r.get("onet_task_count"))
        has_signal = r.get("in_aei", "").lower() == "true" and n is not None
        result.append({
            "task":    short_label(r["task_text"]),
            "full":    r["task_text"],
            "auto":    safe_float(r.get("automation_pct"))   if has_signal else None,
            "aug":     safe_float(r.get("augmentation_pct")) if has_signal else None,
            "success": safe_float(r.get("task_success_pct")) if has_signal else None,
            "n":       n if has_signal else None,
        })
    return result

def render_task_row(t):
    task    = t["task"].replace('"', '\\"').replace("…", "…")
    full    = t["full"].replace('"', '\\"')
    auto    = fmt(t["auto"])
    aug     = fmt(t["aug"])
    success = fmt(t["success"])
    n       = fmt(t["n"])
    # Pad task label to ~32 chars for alignment
    task_str = f'"{task}"'
    return f'    {{ task: {task_str:<36}, full: "{full}", auto: {auto}, aug: {aug}, success: {success}, n: {n} }},'

def build_task_data_block(tasks):
    rows = "\n".join(render_task_row(t) for t in tasks)
    return f"  taskData: [\n{rows}\n  ],"

def patch_tsx(path: Path, tasks: list) -> bool:
    content = path.read_text(encoding="utf-8")
    new_block = build_task_data_block(tasks)
    # Match taskData: [ ... ], including multiline
    pattern = re.compile(r"  taskData: \[.*?\n  \],", re.DOTALL)
    if not pattern.search(content):
        print(f"  ! Could not find taskData block in {path.name}")
        return False
    new_content = pattern.sub(new_block, content)
    if new_content == content:
        print(f"  = No change: {path.name}")
        return False
    path.write_text(new_content, encoding="utf-8")
    return True

def main():
    task_table = load_task_table()
    updated = []
    skipped = []

    for slug, code in SLUG_TO_CODE.items():
        tsx_path = CAREERS_DIR / f"{slug}.tsx"
        if not tsx_path.exists():
            print(f"  ? Missing: {slug}.tsx")
            continue
        rows = task_table.get(code, [])
        if not rows:
            print(f"  ? No task data for {code} ({slug})")
            continue
        tasks = build_task_data(rows)
        changed = patch_tsx(tsx_path, tasks)
        if changed:
            updated.append(slug)
            print(f"  + Updated: {slug}.tsx")
        else:
            skipped.append(slug)

    print(f"\nDone. {len(updated)} updated, {len(skipped)} unchanged.")

if __name__ == "__main__":
    main()
