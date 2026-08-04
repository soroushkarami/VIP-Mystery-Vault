from django import forms
from .models import Store
from .normalizer import persian_to_english_numbers, normalize_size
from django.contrib.auth.models import User


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
        user = kwargs.pop('user', None)     # Get the logged-in user(seller) from kwarg dict
        super().__init__(*args, **kwargs)
        if user:    # if the user exists, only show his stores to him
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

    def clean_phone(self):    # runs automatically when form.is_valid() is called
        phone = self.cleaned_data['phone']
        phone = persian_to_english_numbers(phone)
        phone = ''.join([ch for ch in phone if ch.isdigit()])

        # TODO 1: length check
        if len(phone) != 11:
            raise forms.ValidationError('شماره موبایل باید ۱۱ رقم باشد.')

        # TODO 2: check if it starts with 09
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

    def clean_size(self):    # runs automatically when form.is_valid() is called
        size = self.cleaned_data['size']
        return normalize_size(size)


class UsernameChangeForm(forms.Form):
    new_username = forms.CharField(
        max_length=120,
        label='New Username',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new username'
        })
    )

    confirm_username = forms.CharField(
        max_length=120,
        label='Confirm Username',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Re-enter new username'
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)   # Calls the parent class (forms.Form) to do its normal setup (ie creating the form):
        # Creates the fields, Binds the data (post,get), Sets up validation (so form.is_valid works), Prepares 'cleaned_data'

    def clean_new_username(self):   # runs automatically when form.is_valid() is called
        new_useraname = self.cleaned_data['new_username']
        if User.objects.filter(username=new_useraname).exclude(id=self.user.id).exists():
            raise forms.ValidationError('Username already taken! Try something else please.')
        return new_useraname

    def clean(self):    # runs automatically when form.is_valid() is called
        cleaned_data = super().clean()
        new_username = cleaned_data.get('new_username')
        confirm_username = cleaned_data.get('confirm_username')
        if new_username and confirm_username and new_username != confirm_username:
            raise forms.ValidationError('Usernames do not match! Re-enter the same username please')
        return cleaned_data