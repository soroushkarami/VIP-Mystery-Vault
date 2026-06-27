from django import forms
from .models import Store
from .normalizer import persian_to_english_numbers, normalize_size


class UploadInventoryForm(forms.Form):
    # Create a dropdown menu on the page
    store = forms.ModelChoiceField(
        queryset=Store.objects.none(),  # Empty by default
        label='Select Store'
    )
    # Create a file upload button on the page
    excel_file = forms.FileField(label="Excel File (.xlsx)")
    zip_images = forms.FileField(required=False,        # optional
                                 label="ZIP File with Photos")

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)     # Get the logged-in user(seller)
        super().__init__(*args, **kwargs)
        if user:
            # Only show this user's stores to him
            self.fields['store'].queryset = Store.objects.filter(user=user)


class CustomerRegistrationForm(forms.Form):
    phone = forms.CharField(
        max_length=15,
        label='شماره موبایل',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '09123456789',
            'dir': 'rtl'
        })
    )

    size = forms.ChoiceField(
        choices=[('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL'), ('XXL', 'XXL'), ('XXXL', 'XXXL')],
        label='سایز',
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        phone = persian_to_english_numbers(phone)
        phone = ''.join([ch for ch in phone if ch.isdigit()])

        # TODO 1: length check
        if len(phone) != 11:
            raise forms.ValidationError('شماره موبایل باید ۱۱ رقم باشد.')

        # TODO 2: checkif it starts with 09
        if not phone.startswith('09'):
            raise forms.ValidationError('شماره موبایل باید با ۰۹ شروع شود.')

        # TODO 3: check Iranian mobile prefixes
        valid_prefixes = [
            # hamrahe avval
            '0910', '0911', '0912', '0913', '0914', '0915', '0916',
            '0917', '0918', '0919', '0990', '0991', '0992', '0993',
            '0994', '0996',
            # irancell
            '0900', '0901', '0902', '0903', '0904', '0905', '0930',
            '0933', '0935', '0936', '0937', '0938', '0939', '0941',
            # rightel                                             
            '0920', '0921', '0922', '0923',
            # uptel
            '0999',
        ]

        prefix = phone[:4]
        if prefix not in valid_prefixes:
            raise forms.ValidationError('شماره موبایل معتبر نیست (پیش‌شماره اشتباه).')

        return phone

    def clean_size(self):
        size = self.cleaned_data['size']
        return normalize_size(size)
