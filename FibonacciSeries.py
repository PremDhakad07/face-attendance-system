import sys

def display_menu():
    print("\n=== Supermarket Management System ===")
    print("1. Add Products")
    print("2. View Products")
    print("3. Search Product")
    print("4. Remove Product")
    print("5. Generate Bill")
    print("6. Exit")

def add_product(products):
    print("\n=== Add Products ===")
    while True:
        product_id = input("Enter product ID (or type 'done' to finish): ")
        if product_id.lower() == 'done':
            break
        if product_id in products:
            print("Product ID already exists. Try again.")
            continue
        name = input("Enter product name: ")
        try:
            price = float(input("Enter product price: "))
            quantity = int(input("Enter product quantity: "))
        except ValueError:
            print("Invalid input for price or quantity. Please try again.")
            continue
        products[product_id] = {"name": name, "price": price, "quantity": quantity}
        print(f"Product '{name}' added successfully!")

def view_products(products):
    if not products:
        print("No products available.")
        return
    print("\n=== Product List ===")
    for product_id, details in products.items():
        print(f"ID: {product_id}, Name: {details['name']}, Price: {details['price']}, Quantity: {details['quantity']}")

def search_product(products):
    product_id = input("Enter product ID to search: ")
    if product_id in products:
        details = products[product_id]
        print(f"ID: {product_id}, Name: {details['name']}, Price: {details['price']}, Quantity: {details['quantity']}")
    else:
        print("Product not found.")

def remove_product(products):
    product_id = input("Enter product ID to remove: ")
    if product_id in products:
        del products[product_id]
        print("Product removed successfully!")
    else:
        print("Product not found.")

def generate_bill(products):
    print("\n=== Generate Bill ===")
    if not products:
        print("No products available to generate a bill.")
        return
    cart = {}
    while True:
        product_id = input("Enter product ID to add to cart (or 'done' to finish): ")
        if product_id.lower() == 'done':
            break
        if product_id in products:
            try:
                quantity = int(input("Enter quantity: "))
            except ValueError:
                print("Invalid quantity. Please try again.")
                continue
            if quantity <= products[product_id]['quantity']:
                if product_id not in cart:
                    cart[product_id] = {"name": products[product_id]['name'], "price": products[product_id]['price'], "quantity": 0}
                cart[product_id]['quantity'] += quantity
                products[product_id]['quantity'] -= quantity
                print(f"Added {quantity} of {products[product_id]['name']} to cart.")
            else:
                print("Insufficient stock available.")
        else:
            print("Product not found.")
    
    print("\n=== Bill Details ===")
    total = 0
    for product_id, details in cart.items():
        item_total = details['price'] * details['quantity']
        print(f"{details['name']} (x{details['quantity']}): ${item_total:.2f}")
        total += item_total
    print(f"Total Amount: ${total:.2f}")

def main():
    products = {}
    while True:
        display_menu()
        choice = input("Enter your choice: ")
        if choice == '1':
            add_product(products)
        elif choice == '2':
            view_products(products)
        elif choice == '3':
            search_product(products)
        elif choice == '4':
            remove_product(products)
        elif choice == '5':
            generate_bill(products)
        elif choice == '6':
            print("Exiting the program. Goodbye!")
            sys.exit()
        else:
            print("Invalid choice. Please try again.")

if __name__ == "_main_":
    main()