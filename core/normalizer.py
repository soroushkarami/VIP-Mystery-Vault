# -------------------------------------------------------------------
# 1. COLUMN MAPPING (Persian Excel headers → English)
# -------------------------------------------------------------------
COLUMN_MAPPING = {
    # Common Persian headers
    'کد کالا': 'Sku',
    'کد': 'Sku',
    'نام کالا': 'Name',
    'نام': 'Name',
    'قیمت': 'Price',
    'قیمت فروش': 'Price',
    'موجودی': 'Stock',
    'تعداد': 'Stock',
    'دسته بندی': 'Category',
    'دسته': 'Category',
    'گروه': 'Category',
    'سایز': 'Size',
    'اندازه': 'Size',
    'سایز محصول': 'Size',
}


# -------------------------------------------------------------------
# 2. SIZE MAPPING (Persian sizes → English codes)
# -------------------------------------------------------------------
SIZE_MAPPING = {
    # Persian to English
    'اس': 'S',
    'س': 'S',
    'اسمال': 'S',
    'کوچک': 'S',

    'متوسط': 'M',
    'ام': 'M',
    'م': 'M',
    'مدیوم': 'M',

    'بزرگ': 'L',
    'ال': 'L',
    'ل': 'L',
    'لارج': 'L',

    'خیلی بزرگ': 'XL',
    'اکس‌ال': 'XL',
    'ایکس‌ال': 'XL',
    'اکس لارج': 'XL',
    'ایکس لارج': 'XL',

    'ایکس ایکس ال': 'XXL',
    'اکس اکس ال': 'XXL',
    'خیلی خیلی بزرگ': 'XXL',
    'دو اکس لارج': 'XXL',
    'دو ایکس لارج': 'XXL',

    'ایکس ایکس ایکس ال': 'XXXL',
    'اکس اکس اکس ال': 'XXXL',
    'سه اکس لارج': 'XXXL',
    'سه ایکس لارج': 'XXXL',
}


# -------------------------------------------------------------------
# 3. HELPER FUNCTIONS
# -------------------------------------------------------------------
def normalize_columns(df):
    """
    Convert Persian column names to English.
    """
    new_columns = []
    for col in df.columns:
        col = col.strip()
        if col in COLUMN_MAPPING:
            new_columns.append(COLUMN_MAPPING[col])
        else:
            # Fallback: just clean it up
            new_columns.append(col.capitalize())
    df.columns = new_columns
    return df


def persian_to_english_numbers(text):
    """
    Convert Persian digits (۰۱۲۳۴۵۶۷۸۹) to English digits (0123456789).
    Also removes Persian and English commas.
    """
    if not text:
        return text

    # Define translation table
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    trans = str.maketrans(persian_digits, english_digits)

    # Remove commas (both Persian and English) and trim whitespace
    text = str(text).replace('،', '').replace(',', '').strip()

    return text.translate(trans)


def normalize_size(size):
    """
    Convert Persian size names to English codes (S, M, L, XL, XXL, XXXL).
    If the size is already English, it returns it directly (case-insensitive).
    """
    if not size:
        return 'M'

    # 1. Strip spaces
    size = str(size).strip()

    # 2. Check for English sizes (e.g., 'xl', 'L', 'xxl')
    if size.upper() in ['S', 'M', 'L', 'XL', 'XXL', 'XXXL']:
        return size.upper()  # Return standard English code

    # 3. Check for Persian sizes
    for persian, english in SIZE_MAPPING.items():
        # Direct check: Does the Persian key exist in the input?
        if persian in size:
            return english

    # 4. If nothing matches, default to 'M'
    return 'M'
