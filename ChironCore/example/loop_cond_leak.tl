:out = 0
repeat :n [
  if :secret > 5 [
    :out = :out + 2
  ] else [
    :out = :out + 1
  ]
]