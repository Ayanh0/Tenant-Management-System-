file = open("lib.txt", "r")
lines = file.readlines()
file.close()
books = []
users = []
days_list = []
for line in lines:
    parts = line.strip().split(",")
    books.append(parts[0])
    users.append(parts[1])
    days_list.append(int(parts[2]))
print("Borrowed Books:")
for i in range(len(books)):
    print(books[i], "by", users[i])
count = {}
for book in books:
    if book in count:
        count[book] += 1
    else:
        count[book] = 1
max_book = ""
max_count = 0
for book in count:
    if count[book] > max_count:
        max_count = count[book]
        max_book = book
print("\nMost Borrowed Book:", max_book)
print("\nOverdue Users (Days > 10):")
for i in range(len(days_list)):
    if days_list[i] > 10:
        print(users[i], "-", books[i])