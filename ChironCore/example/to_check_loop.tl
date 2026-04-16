:acc1 = 0
:acc2 = 0
:temp = :secret + :pub
@@ :acc1
@@ :temp - :secret
repeat :n [
  :acc1 = :acc1 + :temp - :secret
  :temp = :temp + 1
]