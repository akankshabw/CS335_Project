:a = 0
:b = 0
:out = 0
@@ :a
repeat :n [
  :a = :a + :pub
]
@@ :b
@@ :b - :a
repeat :n [
  :b = :b + :pub
]
@@ :a
@@ :b
repeat :n [
  :out = :out + :a + :b
]
