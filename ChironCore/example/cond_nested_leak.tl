:out = 0
if :pub > 50 [
  if :secret > 3 [
    :out = 1
  ] else [
    :out = 2
  ]
] else [
  :out = 3
]