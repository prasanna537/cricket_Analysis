"""Turns the retention lists supplied by the user (18 Nov 2026) into retention_lists_2027.csv (team, player_name_supplied, traded_in)."""
import csv
from pathlib import Path

RAW = {
    "Chennai Super Kings": """Sanju Samson|Ruturaj Gaikwad|Ayush Mhatre|Dewald Brevis|Urvil Patel|Kartik Sharma|Sarfaraz Khan|Anshul Kamboj|Gurjapneet Singh|Mukesh Choudhary|Noor Ahmad|Rahul Chahar|Jamie Overton|Ramakrishna Ghosh|Shivam Dube|Shreyas Gopal|Akeal Hosein|Liam Livingstone|Jack Edwards*""",
    "Delhi Capitals": """Ashutosh Sharma|KL Rahul|Sameer Rizvi|Tristan Stubbs|David Miller|Prithvi Shaw|Mukesh Kumar|Tripurana Vijay|Auqib Nabi|Axar Patel|Madhav Tiwari|Vipraj Nigam|Rishabh Pant*|Zeeshan Ansari*""",
    "Gujarat Titans": """Anuj Rawat|Jos Buttler|Kumar Kushagra|Sai Sudharsan|Shubman Gill|Tom Banton|Gurnoor Brar|Kagiso Rabada|Mohammed Siraj|Arshad Khan|Prasidh Krishna|Sai Kishore|Rashid Khan|Ashok Sharma|Prithvi Raj Yarra|Glenn Phillips|Jayant Yadav|Manav Suthar|Nishant Sindhu|Rahul Tewatia|Washington Sundar|Jason Holder|Harshal Patel*""",
    "Kolkata Knight Riders": """Angkrish Raghuvanshi|Manish Pandey|Rinku Singh|Rovman Powell|Finn Allen|Tim Seifert|Harshit Rana|Vaibhav Arora|Varun Chakaravarthy|Kartik Tyagi|Prashant Solanki|Anukul Roy|Ramandeep Singh|Sunil Narine|Cameron Green|Sarthak Ranjan|Daksh Kamra""",
    "Lucknow Super Giants": """Abdul Samad|Himmat Singh|Nicholas Pooran|Mukul Choudhary|Akshat Raghuwanshi|Josh Inglis|Akash Singh|Arjun Tendulkar|Digvesh Rathi|Mayank Yadav|Mohsin Khan|Prince Yadav|Aiden Markram|Ayush Badoni|Mitchell Marsh|Kuldeep Yadav*|Sam Curran*""",
    "Mumbai Indians": """Robin Minz|Rohit Sharma|Ryan Rickelton|Sherfane Rutherford|Suryakumar Yadav|Tilak Varma|Quinton de Kock|Ashwani Kumar|Jasprit Bumrah|Raghu Sharma|Shardul Thakur|Corbin Bosch|Mitchell Santner|Naman Dhir|Raj Bawa|Will Jacks|Arshdeep Singh*""",
    "Punjab Kings": """Harnoor Singh Pannu|Prabhsimran Singh|Priyansh Arya|Shashank Singh|Shreyas Iyer|Vishnu Vinod|Vyshak Vijaykumar|Xavier Bartlett|Yash Thakur|Yuzvendra Chahal|Ben Dwarshius|Azmatullah Omarzai|Harpreet Brar|Marco Jansen|Marcus Stoinis|Musheer Khan|Suryansh Shedge|Cooper Connolly|Hardik Pandya*""",
    "Rajasthan Royals": """Dhruv Jurel|Lhuan-dre Pretorius|Shubham Dubey|Vaibhav Suryavanshi|Aman Rao|Jofra Archer|Nandre Burger|Sandeep Sharma|Ravi Bishnoi|Sushant Mishra|Yash Raj Punja|Brijesh Sharma|Donovan Ferreira|Ravindra Jadeja|Riyan Parag|Mohammed Shami*|Manimaran Siddharth*""",
    "Royal Challengers Bengaluru": """Devdutt Padikkal|Jitesh Sharma|Phil Salt|Rajat Patidar|Tim David|Virat Kohli|Jordan Cox|Abhinandan Singh|Bhuvneshwar Kumar|Josh Hazlewood|Nuwan Thushara|Rasikh Dar|Suyash Sharma|Yash Dayal|Jacob Duffy|Vicky Ostwal|Krunal Pandya|Romario Shepherd|Swapnil Singh|Venkatesh Iyer|Kanishk Chouhan""",
    "Sunrisers Hyderabad": """Aniket Verma|Heinrich Klaasen|Ishan Kishan|Smaran Ravichandran|Salil Arora|Brydon Carse|Eshan Malinga|Pat Cummins|Sakib Hassan|Praful Hinge|Abhishek Kumar|Harsh Dubey|Nitish Kumar Reddy|Shivang Kumar|Krains Fuletra|Khaleel Ahmed|Nathan Ellis*""",
}
# expected counts as supplied: CSK 19 (18 + traded in), DC 14, GT 23, KKR 17, LSG 17, MI 17, PBKS 19, RR 17, RCB 21, SRH 17
EXPECT = {"Chennai Super Kings": 19, "Delhi Capitals": 14, "Gujarat Titans": 23, "Kolkata Knight Riders": 17, "Lucknow Super Giants": 17,
          "Mumbai Indians": 17, "Punjab Kings": 19, "Rajasthan Royals": 17, "Royal Challengers Bengaluru": 21, "Sunrisers Hyderabad": 17}
# Corrections supplied by the user after the first paste (the pasted lists were incomplete):
#  - RR: Dasun Shanaka and Yashasvi Jaiswal appear on the official RR "Retained" graphic (user screenshot, 18 Nov 2026)
#  - LSG: Shahbaz Ahmed is on the LSG retained list (user statement, 18 Nov 2026)
CORRECTIONS = [
    ("Rajasthan Royals", "Dasun Shanaka", False, "user correction 18 Nov 2026 (RR retained graphic)"),
    ("Rajasthan Royals", "Yashasvi Jaiswal", False, "user correction 18 Nov 2026 (RR retained graphic)"),
    ("Lucknow Super Giants", "Shahbaz Ahmed", False, "user correction 18 Nov 2026 (LSG retained list)"),
]
rows = []
for team, s in RAW.items():
    names = s.split("|")
    assert len(names) == EXPECT[team], (team, len(names), EXPECT[team])
    for n in names:
        rows.append(dict(team=team, player_name_supplied=n.rstrip("*"), traded_in=n.endswith("*"), source="pasted list"))
for t_, n_, tr_, src_ in CORRECTIONS:
    rows.append(dict(team=t_, player_name_supplied=n_, traded_in=tr_, source=src_))
out = Path(r"d:\IPl\retention_lists_2027.csv")
with out.open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["team", "player_name_supplied", "traded_in", "source"])
    w.writeheader(); w.writerows(rows)
print(len(rows), "rows written;", {t: sum(r["team"] == t for r in rows) for t in RAW})
