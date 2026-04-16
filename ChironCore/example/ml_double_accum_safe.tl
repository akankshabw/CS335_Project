:acc1 = 0
:acc2 = 0
@@ :acc1
repeat :n [
  :acc1 = :acc1 + :pub
]
@@ :acc2
@@ :acc2 - :acc1
repeat :n [
  :acc2 = :acc2 + :pub
]
