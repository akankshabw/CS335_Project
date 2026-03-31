:out = 0
:x = :secret
:y = :secret + :pub
@@ :out
@@ :y - :x
repeat :n [
  :x = :x + :pub
  :y = :y + :pub
  :out = :out + :y - :x
]