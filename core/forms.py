from django import forms
from .models import Store
from .normalizer import persian_to_english_numbers, normalize_size


class UploadInventoryForm(forms.Form):
    # Create a dropdown menu on the page
    store = forms.ModelChoiceField(queryset=Store.objects.all(),    # Admin can see all stores
                                   label='Select Store')
    # Create a file upload button on the page
    excel_file = forms.FileField(label="Excel File (.xlsx)")
    zip_images = forms.FileField(required=False,        # optional
                                 label="ZIP File with Photos")


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

        # Step 1: Convert Persian digits to English
        phone = persian_to_english_numbers(phone)

        # Step 2: Remove all non-digit characters
        phone = ''.join([ch for ch in phone if ch.isdigit()])

        # Step 3: Validate length
        if len(phone) < 10:
            raise forms.ValidationError('شماره موبایل معتبر نیست.')

        return phone

    def clean_size(self):
        size = self.cleaned_data['size']
        return normalize_size(size)
