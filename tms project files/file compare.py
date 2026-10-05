def compare_files(file1, file2):
    with open(file1, 'r') as f1:
        lines1 = f1.readlines()
    with open(file2, 'r') as f2:
        lines2 = f2.readlines()
    lines1 = [line.strip() for line in lines1]
    lines2 = [line.strip() for line in lines2]
    set1 = set(lines1)
    set2 = set(lines2)
    common = set1.intersection(set2)
    unique1 = set1 - set2
    unique2 = set2 - set1
    total = len(set1.union(set2))
    similarity = (len(common) / total) * 100 if total != 0 else 0
    print("\nCommon Lines:")
    for line in common:
        print(line)
    print("\nUnique in File 1:")
    for line in unique1:
        print(line)
    print("\nUnique in File 2:")
    for line in unique2:
        print(line)
    print("\nSimilarity: {:.2f}%".format(similarity))
file1 = input("Enter first file name: ")
file2 = input("Enter second file name: ")
compare_files(file1, file2)