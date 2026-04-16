:sum = 0
:diff = 0
:temp = :secret + :pub
@@ :sum
@@ :temp - :secret
repeat :n [
  :sum = :sum + :temp - :secret
  :temp = :temp + 1
]
:diff = :diff + :temp
@@ :diff
@@ :temp - :secret
repeat :n [
  :diff = :diff + :temp - :secret
  :temp = :temp - 1
]
