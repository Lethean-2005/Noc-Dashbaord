"""Append verified missing work to the existing tracker without rewriting history."""
from pathlib import Path
from copy import copy, deepcopy
from collections import Counter
from datetime import datetime
import json
import os
import shutil
import math
import zipfile

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.comments import Comment

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "docs/reference/NOC-DASHBORD.xlsx"
DATA = ROOT / "docs/reference"


def extend_conditional_formatting(sheet, last_row):
    for item in list(sheet.conditional_formatting):
        rules = deepcopy(sheet.conditional_formatting[item])
        ranges = str(item.sqref).split()
        del sheet.conditional_formatting[str(item.sqref)]
        for cell_range in ranges:
            left, top, right, _bottom = range_boundaries(cell_range)
            target = f"{get_column_letter(left)}{top}:{get_column_letter(right)}{last_row}"
            for rule in rules:
                sheet.conditional_formatting.add(target, deepcopy(rule))


def clone_row(sheet, template, target, last_column):
    for column in range(1, last_column + 1):
        src, dst = sheet.cell(template, column), sheet.cell(target, column)
        dst._style = copy(src._style)
        dst.alignment = Alignment(horizontal="left" if column in (1,3,last_column) else "center",
                                  vertical="center", wrap_text=True)
        dst.font = Font(name="Huawei Sans", size=8.5)
        dst.fill = PatternFill("solid", fgColor="FFFFFF")
    sheet.row_dimensions[target].height = 36


def set_readable_rows(sheet, last_column):
    for row in sheet.iter_rows(min_row=2, max_col=last_column):
        lines = 1
        for cell in row:
            if cell.value is None:
                continue
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            alignment.vertical = "center"
            cell.alignment = alignment
            width = sheet.column_dimensions[cell.column_letter].width or 12
            value = str(cell.value)
            lines = max(lines, sum(max(1, math.ceil(len(line) / max(5, width-3)))
                                   for line in value.splitlines()))
        sheet.row_dimensions[row[0].row].height = max(27, min(84, lines*12+12))
    sheet.freeze_panes = "A2"
    sheet.print_title_rows = "1:1"
    sheet.print_area = f"A1:{get_column_letter(last_column)}{sheet.max_row}"
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0


def main():
    tasks = json.loads((DATA / "task-tracker-update-data.json").read_text(encoding="utf-8"))
    issues = json.loads((DATA / "task-tracker-issue-data.json").read_text(encoding="utf-8"))
    workbook = load_workbook(WORKBOOK)
    sheet, issue_sheet, notes = workbook["Noc Dashbord"], workbook["Issue Lists"], workbook["Others"]
    original = {s.title: {(cell.row, cell.column): cell.value for row in s for cell in row
                          if cell.value is not None} for s in (sheet, issue_sheet)}
    original_merges = set(map(str,sheet.merged_cells.ranges))
    backup_dir = DATA / "backups"
    backup_dir.mkdir(exist_ok=True)
    backup = backup_dir / (WORKBOOK.stem + "-before-update-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".xlsx")
    shutil.copy2(WORKBOOK, backup)
    task_names = {str(sheet.cell(row,3).value): row for row in range(2,sheet.max_row+1)}
    next_task = max(int(str(sheet.cell(row,2).value)[1:]) for row in range(2,sheet.max_row+1)) + 1
    phase_ranges = []
    added_tasks=[]
    for task in tasks:
        if task["name"] in task_names:
            continue
        row=sheet.max_row+1
        clone_row(sheet,72,row,13)
        task_id=f"T{next_task}"
        next_task+=1
        values=[task["phase"],task_id,task["name"],"S. Lethean","Egineer",
                task.get("date"),None,task.get("dependency","-"),task["priority"],
                1 if task["status"]=="Completed" else 0,task["status"],"-",task["remarks"]]
        for column,value in enumerate(values,1):sheet.cell(row,column,value)
        sheet.cell(row,10).number_format="0%"
        sheet.cell(row,6).comment=Comment("Actual start date was not supplied. Left blank rather than inventing a schedule. Logged in the 11-Nov-2026 tracker review.","Tracker update")
        sheet.cell(row,7).comment=Comment("Actual duration was not supplied; no estimate has been represented as actual effort.","Tracker update")
        task_names[task["name"]]=row
        added_tasks.append((task_id,row,task))
        if phase_ranges and phase_ranges[-1][0]==task["phase"]:
            phase_ranges[-1][2]=row
        else:phase_ranges.append([task["phase"],row,row])
    # Link only concrete implementation dependencies, not a fabricated sequential chain.
    names_to_ids={sheet.cell(row,3).value:sheet.cell(row,2).value for row in range(2,sheet.max_row+1)}
    dependencies={
        "All-resolved incident drilldown and export":"All WO is Resolved badge and source-flag verification",
        "All-resolved cache refresh and table continuity":"All WO is Resolved badge and source-flag verification",
        "All-resolved badge placement and labels":"All WO is Resolved badge and source-flag verification",
        "Optional exclusion remark and validation":"Narrow exclusions to one device/interface",
        "Expanded blacklist table and Restore workflow":"Persistent local congestion exclusions",
        "SLA root-cause matching drilldown and export":"SLA root-cause failures: Response and Resolution",
        "Wider SLA popup with bordered example table":"SLA root-cause failures: Response and Resolution",
        "Separate Feature Guide PDF with screenshots":"Practical action and feature usage guides",
        "Nine real-interface screenshot demonstrations":"Practical action and feature usage guides",
    }
    for task_id,row,task in added_tasks:
        if task["name"] in dependencies:sheet.cell(row,8,names_to_ids[dependencies[task["name"]]])
    for phase,start,end in phase_ranges:
        if end>start:sheet.merge_cells(start_row=start,start_column=1,end_row=end,end_column=1)
        sheet.cell(start,1).alignment=Alignment(vertical="center",horizontal="left",wrap_text=True)

    issue_names={str(issue_sheet.cell(row,2).value) for row in range(2,issue_sheet.max_row+1)}
    next_issue=max(int(str(issue_sheet.cell(row,1).value).split("-")[-1]) for row in range(2,issue_sheet.max_row+1))+1
    added_issues=[]
    for issue in issues:
        if issue["name"] in issue_names:continue
        row=issue_sheet.max_row+1
        clone_row(issue_sheet,27,row,9)
        issue_id=f"ISSUE-{next_issue:03d}"
        next_issue+=1
        values=[issue_id,issue["name"],"Enginering",None,None,issue["priority"],
                1 if issue["status"]=="Completed" else 0,issue["remark"],issue["status"]]
        for column,value in enumerate(values,1):issue_sheet.cell(row,column,value)
        issue_sheet.cell(row,7).number_format="0%"
        issue_names.add(issue["name"])
        added_issues.append((issue_id,row,issue))

    # Retain the template's column order, header colors and Huawei Sans styling.
    sheet.column_dimensions["M"].width=90
    sheet.column_dimensions["K"].width=15
    sheet.column_dimensions["F"].width=14
    issue_sheet.column_dimensions["B"].width=54
    issue_sheet.column_dimensions["H"].width=96
    issue_sheet.column_dimensions["I"].width=15
    extend_conditional_formatting(sheet,sheet.max_row)
    extend_conditional_formatting(issue_sheet,issue_sheet.max_row)
    gray=PatternFill("solid",fgColor="EEF0F3")
    sheet.conditional_formatting.add(f"K2:K{sheet.max_row}",FormulaRule(formula=['K2="Not Started"'],fill=gray))
    issue_sheet.conditional_formatting.add(f"I2:I{issue_sheet.max_row}",FormulaRule(formula=['I2="Not Started"'],fill=gray))
    set_readable_rows(sheet,13)
    set_readable_rows(issue_sheet,9)

    if notes.max_row==1 and notes.cell(1,1).value is None:
        note_rows=[
            ("Tracker update", "11-Nov-2026"),
            ("Scope", "Missing work after T71 and ISSUE-026, reviewed against repository files and the recorded work in this session."),
            ("New task rows",len(added_tasks)),
            ("New issue rows",len(added_issues)),
            ("Existing history", "Existing task and issue cell values and original phase merges were preserved. Obsolete intermediate design attempts are consolidated into the final delivered task."),
            ("Start dates and durations", "Actual timing for the appended records was not supplied. Start Date, Issue Date, Duration and actual variance are left blank or marked '-' instead of inventing dates/effort."),
            ("Ownership", "New records follow the existing S. Lethean / Egineer / Enginering labels in the template."),
            ("Completed", "Implemented or produced and checked locally. Does not mean every change is installed on the VM or externally confirmed."),
            ("In Progress", "An identified item remains unfinished. 0% on new open items means no accepted completion percentage was supplied; it is not a measured effort percentage."),
            ("Not Started", "Deferred, proposed, or awaiting an external change; not represented as delivered."),
            ("Latest ZIP", "Nov-10 V51 was verified for that build. Later Help, screenshot and separate PDF changes are not included in that ZIP."),
            ("Teams delivery", "Webhook acceptance is distinct from successful completion of the Power Automate/Teams/SharePoint steps."),
            ("Existing T47", "Original generic graph/query task remains In Progress at 0%; its exact original scope is unclear, so it was not silently closed."),
            ("Existing progress anomalies", "ISSUE-001 is Completed with Progress 0.5; ISSUE-020 is Completed with Progress 2. Historical values preserved; owner review recommended."),
            ("Version numbering", "Semver naming was discussed but deferred. No new 19.x version or migration is claimed."),
            ("Verification limits", "Local regression, rendering and archive checks are evidence for their stated scope, not a VM load test or a guarantee against every bug."),
            ("Backup",str(backup.relative_to(ROOT))),
        ]
        notes.cell(1,1,"Field")
        notes.cell(1,2,"Update notes")
        for row in note_rows:notes.append(list(row))
        for cell in notes[1]:
            cell.font=Font(name="Huawei Sans",size=9,bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="1B3A6B")
        notes.column_dimensions["A"].width=29
        notes.column_dimensions["B"].width=115
        for row in notes.iter_rows(min_row=2):
            for cell in row:
                cell.font=Font(name="Huawei Sans",size=9)
                cell.alignment=Alignment(vertical="top",wrap_text=True)
                cell.border=Border(bottom=Side(style="thin",color="E1E5EB"))
            notes.row_dimensions[row[0].row].height=42
        notes.freeze_panes="A2"
        notes.print_area=f"A1:B{notes.max_row}"

    # Assert the update did not rewrite any original task/issue values.
    for title,cells in original.items():
        for (row,column),value in cells.items():
            assert workbook[title].cell(row,column).value==value,(title,row,column)
    assert original_merges.issubset(set(map(str,sheet.merged_cells.ranges)))
    temp=WORKBOOK.with_name(WORKBOOK.stem+".updating.xlsx")
    workbook.save(temp)
    with zipfile.ZipFile(temp) as archive:assert archive.testzip() is None
    check=load_workbook(temp)
    assert check.sheetnames==workbook.sheetnames
    for title,cells in original.items():
        for (row,column),value in cells.items():assert check[title].cell(row,column).value==value
    for current,id_col in ((check["Noc Dashbord"],2),(check["Issue Lists"],1)):
        ids=[current.cell(row,id_col).value for row in range(2,current.max_row+1)]
        assert len(ids)==len(set(ids))
    os.replace(temp,WORKBOOK)
    print(f"Updated {WORKBOOK}")
    print(f"Added tasks: {len(added_tasks)}; added issues: {len(added_issues)}")
    print("Task status counts:",dict(Counter(sheet.cell(row,11).value for row in range(2,sheet.max_row+1))))
    print("Issue status counts:",dict(Counter(issue_sheet.cell(row,9).value for row in range(2,issue_sheet.max_row+1))))
    print("Backup:",backup)


if __name__=="__main__":main()
