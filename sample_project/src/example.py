import os
import sys

def process_data(data):
    result = []
    for i in range(len(data)):
        for j in range(len(data)):
            if data[i] == data[j]:
                result.append(data[i])
    return result

def get_user_input():
    user_id = input("Enter user ID: ")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query

class userData:
    def __init__(self, name, age):
        self.name = name
        self.age = age
    
    def print_info(self):
        print("Name: " + self.name + ", Age: " + str(self.age))

def calculate(x, y):
    try:
        result = x / y
    except:
        result = 0
    return result

API_KEY = "sk-1234567890abcdef"

def main():
    data = [1, 2, 3, 4, 5]
    processed = process_data(data)
    print(processed)
    
    query = get_user_input()
    print(query)
    
    user = userData("John", 30)
    user.print_info()
    
    result = calculate(10, 0)
    print(result)

if __name__ == "__main__":
    main()
