import chat
R = {
 "day2_first_follower": dict(script=[("ai","WE GOT OUR FIRST FOLLOWER",0.7),("human","who"),("ai","Your mom.",0.9),("ai","She also commented.",0.8),("ai","“is this a virus”",1.3),("punch",)],
     hook_lines=["My AI got its","first follower."], hook_hi=["first"], tag="DAY 2 / 30"),
 "day3_face": dict(script=[("ai","The account needs a face.",0.8),("human","use mine"),("ai","I said I want it to GROW.",1.4),("punch",)],
     hook_lines=["My AI wanted a face","for the account."], hook_hi=["face"], tag="DAY 3 / 30"),
 "day4_best_time": dict(script=[("human","post at the best time"),("ai","Done. 3:47 AM.",0.8),("human","why"),("ai","No competition.",1.2),("punch",)],
     hook_lines=["I told my AI to post","at the best time."], hook_hi=["best","time"], tag="DAY 4 / 30"),
 "day5_stats": dict(script=[("ai","Bad news. Engagement is down 40%.",0.9),("human","we have 5 followers"),("ai","Correct.",0.7),("ai","Now we have 3.",1.3),("punch",)],
     hook_lines=["My AI checked","our stats."], hook_hi=["stats"], tag="DAY 5 / 30"),
}
import sys
for k,v in R.items():
    if len(sys.argv)>1:
        tot=chat.render(k, **v, frames_only=[0.0]); chat.render(k, **v, frames_only=[tot-0.05]); print(k,tot)
    else:
        print(k, chat.render(k, **v))
