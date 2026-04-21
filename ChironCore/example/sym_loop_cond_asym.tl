:out = 0
repeat :n [
  if :a > :b [
    :out = :out + :a + :a
  ] else [
    :out = :out + :b
  ]
]
