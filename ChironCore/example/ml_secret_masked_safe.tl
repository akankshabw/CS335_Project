:out = 0
:temp = :secret + :pub
@@ :out
@@ :temp - :secret
repeat :n [
  :out = :out + :temp - :secret
  :temp = :temp + :pub
]
@@ :out
@@ :temp - :secret
repeat :n [
  :out = :out + :temp - :secret
  :temp = :temp + :pub
]
