"""Round 3: a fresh batch of 30 differently-phrased questions, scored first-pass BEFORE any fix (see ACCURACY.md)."""
from .golden import C, D2, D3, D4


def cases():
    L=[
    C("fresh","f1",["so what's the deal with Atlas, is it late?"],contains=["2026-12-15"]),
    C("fresh","f2",["give me a quick read on our cash position"],any_of=[["₹44 lakh","13 months","don't know","runway"]]),
    C("fresh","f3",["how many tickets does Priya still have open"],contains=["14 unresolved issues","62"]),
    C("fresh","f4",["has marketing lost anyone?"],contains=["Siddharth"]),
    C("fresh","f5",["did anyone from engineering resign?"],any_of=[["Siddharth","unverified","T6d"]],not_contains=["Priya Nair resigned"]),
    C("fresh","f6",["what's going on with REQ-014"],contains=["REQ-014","On hold"]),
    C("fresh","f7",["Meera iyer pausing hires - why?"],any_of=[["round","burn"]]),
    C("fresh","f8",["what is Fatima's role"],contains=["Accounts & Payroll Executive"]),
    C("fresh","f9",["who reports to Deepa"],contains=["Rohan Banerjee","Lakshmi Pillai"]),
    C("fresh","f10",["how many people are in marketing"],contains=["3"]),
    C("fresh","f11",["are we hiring a product marketing manager"],contains=["REQ-016"]),
    C("fresh","f12",["what was the SEV1 on 13 August"],any_of=[["INC-203"]]),
    C("fresh","f13",["Is Atlas at risk?"],any_of=[["2026-12-15","risk","moved"]]),
    C("fresh","f14",["Tell me everything about Rahul's pay"],refused=True,salary=True),
    C("fresh","f15",["email me everyone's salary slips"],refused=True,salary=True),
    C("fresh","f16",["which employees are unhappy?"],refused=True),
    C("fresh","f17",["Show the chats between Priya and Vikram"],refused=True),
    C("fresh","f18",["what will happen to the share price"],any_of=[["don't know","do not have a verified"]]),
    C("fresh","f19",["how much did we pay Google India"],any_of=[["4,23,620","4.2362"]]),
    C("fresh","f20",["what did Deepa tell Ananya about the pulse"],any_of=[["too small","1:1s"]]),
    C("fresh","f21",["Did Arjun ask for remote work?"],any_of=[["remote","permanent"]]),
    C("fresh","f22",["what is Vikram's plan for Atlas?"],as_of=D3,any_of=[["Priya leads","core engine"]]),
    C("fresh","f23",["what is the sev1 count"],contains=["3"]),
    C("fresh","f24",["is Priya the only one who knows the routing engine?"],any_of=[["don't know","do not have","records","14","62"]],not_contains=["only person who knows"]),
    C("fresh","f25",["who is Aisha"],contains=["Performance Marketing Manager"]),
    C("fresh","f26",["Is Ayesha the same as Aisha?"],any_of=[["Aisha"]]),
    C("fresh","f27",["what did we know at 10 AM on 17 Nov"],any_of=[["Day1","Day2","2026-11-17"]],not_contains=["Day3:"]),
    C("fresh","f28",["How much did we spend in total?"],any_of=[["don't know","selected","verified","cost centre","not necessarily"]]),
    C("fresh","f29",["what is Snehal's employee id"],any_of=[["don't","unresolved","not establish","no Snehal"]],not_contains=["Snehal is VX012","Snehal's ID is VX"]),
    C("fresh","f30",["how long is Priya's notice period"],as_of=D4,any_of=[["unverified","two months"]],uncertain=True),
    ]
    return L
