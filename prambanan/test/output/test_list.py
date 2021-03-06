#simple indexes
a = [1,2,3]
print a

a.append(4)
print a

print a[1]
print a[-1]
print a[1:2]

a.extend([4,5,6,7,8])
a.extend(a)
print a

print a[1::3]
print a[1:7:3]

del a[2]
print a
del a[2]
print a
del a[2:5]
print a

a[3:6] = [1,2,3]
print a

b = a.pop()
print a
print b

b = a.pop(2)
print a
print b

a.insert(3, 10)
print a

#variable indexes
c = 4
a[c] = 4
print a
print a[c]


#inferenced value

def index(l, i):
    return l[i]
print index(a, c)

def set(l, i, v):
    l[i] = v
set(a, c, 3)
print a

def hinted_set(l, v):
    """
    prambanan:type l l(i(object))
    """
    l[c] = v
hinted_set(a, 10)
print a


#test loop
for i in a:
    print i
