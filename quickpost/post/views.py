from django.shortcuts import redirect, render
from .models import Post , Comment, UserProfile
from .forms import PostForm, UserRegistrationForm, UserUpdateForm, ProfileUpdateForm
from django.contrib.auth.decorators import login_required 
from django.contrib.auth import login, authenticate
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.cache import cache
from google import genai
import os
from dotenv import load_dotenv
import re

load_dotenv()
# @login_required
# Create your views here.
def index(request):
    return render(request,'index.html')


#post list view
# @login_required
def post_list(request):
    """
    Display a list of posts and a daily quote.
    The daily quote is automatically refreshed every 12 hours by APScheduler.
    """
    # Get the quote from cache (APScheduler refreshes it every 12 hours)
    quote = cache.get('daily_quote')
    
    # Fallback in case scheduler hasn't run yet or cache is empty
    if not quote:
        quote = get_daily_quote()
        cache.set('daily_quote', quote, None)  # No expiration, scheduler handles refresh
    
    # Parse the quote into text and author
    quote_parts = quote.split(' - ', 1)
    quote_obj = {
        'text': quote_parts[0],
        'author': quote_parts[1] if len(quote_parts) > 1 else 'Unknown'
    }
    
    posts = Post.objects.all().order_by('-created_at')
    return render(request, 'post_list.html', {'posts': posts, 'daily_quote': quote_obj})

#create post view
@login_required
def create_post(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            return redirect('post_list')
    else:
        form = PostForm()
    return render(request, 'create_post.html', {'form': form})

#edit post view
@login_required
def edit_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            return redirect('post_list')
    else:
        form = PostForm(instance=post)
    return render(request, 'create_post.html', {'form': form, 'post': post})

#post delete view
@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, id=post_id, user=request.user)
    if request.method == 'POST':
        post.delete()
        return redirect('post_list')
    return render(request, 'delete_post.html', {'post': post})


def register(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password1'])
            user.save()
            login(request, user)
            return redirect('login')
            
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})


def home(request):
    return render(request, 'index.html')


# def profile(request):
#     if request.user.is_authenticated:

#         posts = Post.objects.filter(user=request.user).order_by('-created_at')
#         return render(request, 'profile.html', {'posts': posts})
#     else:
#         return redirect('login')
@login_required
def profile(request, username):
    user = get_object_or_404(User, username=username)
    posts = Post.objects.filter(user=user).order_by('-created_at')
    
    # Get or create profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Check follow status if user is authenticated and not viewing own profile
    is_following = False
    if request.user.is_authenticated and request.user != user:
        current_profile, created = UserProfile.objects.get_or_create(user=request.user)
        is_following = current_profile.is_following(profile)
    
    context = {
        'profile_user': user,
        'profile': profile,
        'posts': posts,
        'is_own_profile': request.user == user,
        'is_following': is_following,
    }
    return render(request, 'profile.html', context)

@login_required
def edit_profile(request):
    if request.method == 'POST':
        user_form = UserUpdateForm(request.POST, instance=request.user)
        profile_form = ProfileUpdateForm(
            request.POST, 
            request.FILES, 
            instance=request.user.profile
        )
        
        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile', username=request.user.username)
    else:
        user_form = UserUpdateForm(instance=request.user)
        profile_form = ProfileUpdateForm(instance=request.user.profile)
    
    context = {
        'user_form': user_form,
        'profile_form': profile_form,
    }
    return render(request, 'edit_profile.html', context)

@login_required
def like_post(request, post_id):
    if request.method == "POST":
        post = Post.objects.get(id=post_id)
        liked = False

        if request.user in post.likes.all():
            post.likes.remove(request.user)
        else:
            post.likes.add(request.user)
            liked = True

        return JsonResponse({
            "liked": liked,
            "likes_count": post.likes.count()
        })

    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def dislike_post(request, post_id):
    if request.method == "POST":
        try:
            post = Post.objects.get(id=post_id)
        except Post.DoesNotExist:
            return JsonResponse({"error": "Post not found"}, status=404)

        disliked = False

        if request.user in post.dislikes.all():
            post.dislikes.remove(request.user)
        else:
            post.dislikes.add(request.user)
            disliked = True
            # Remove like if it exists
            if request.user in post.likes.all():
                post.likes.remove(request.user)

        return JsonResponse({
            "disliked": disliked,
            "dislikes_count": post.dislikes.count(),
            "likes_count": post.likes.count()
        })

    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def add_comment(request, post_id):
    if request.method == "POST":
        post = Post.objects.get(id=post_id)
        content = request.POST.get("content")
        if content.strip():
            comment = Comment.objects.create(
                post=post,
                user=request.user,
                content=content
            )
            return JsonResponse({
                "success": True,
                "comment_user": comment.user.username,
                "comment_content": comment.content,
                "comment_time": comment.created_at.strftime("%b %d, %Y %H:%M"),
                "comments_count": post.comments.count()
            })
    return JsonResponse({"success": False})



def get_daily_quote():
    """
    Fetches a single inspirational quote from the Gemini API.
    """
    try:
        client = genai.Client(api_key=os.getenv("gemini_api_key"))
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents="write only one quote. Generate a short, impactful one-line quote with a life lesson inspired by the Ramayana and Mahabharata. Keep it clear, simple, and timeless. End with a hyphen followed by the name of the character who said it (e.g., Bhishma, Hanuman, Arjuna, Karna, Draupadi, Rama, Krishna, Sita, etc.). Vary the themes (dharma, truth, courage, devotion, humility, ego, patience)."
        )
        quote = response.text.strip()
        # Remove any unwanted characters or formatting
        quote = re.sub(r'\s+', ' ', quote)
        return quote
    except Exception as e:
        print(f"Error generating quote: {e}")
        # Return a fallback quote in case of API failure
        return "True courage is facing danger when you are afraid. - Krishna"

@require_POST
@login_required
def share_post(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if post.user == request.user:
        return JsonResponse({"error": "You cannot share your own post."}, status=400)

    # Create a new post with the same content and image, but attributed to the sharing user
    shared_post = Post.objects.create(
        user=request.user,
        content=post.content,
        image=post.image,
    )
    return JsonResponse({
        "success": True,
        "shared_post_id": shared_post.id,
        "shared_post_content": shared_post.content,
        "shared_post_image_url": shared_post.image.url if shared_post.image else None,
        "shared_post_user": shared_post.user.username,
        "shared_post_created_at": shared_post.created_at.strftime("%b %d, %Y %H:%M"),
    })

@login_required
@require_POST
def toggle_follow(request, username):
    """Toggle follow/unfollow for a user"""
    try:
        target_user = get_object_or_404(User, username=username)
        
        # Can't follow yourself
        if target_user == request.user:
            return JsonResponse({'error': 'Cannot follow yourself'}, status=400)
        
        # Get or create profiles with error handling
        try:
            current_profile, created = UserProfile.objects.get_or_create(user=request.user)
            if created:
                print(f"Created new profile for {request.user.username}")
        except Exception as e:
            print(f"Error creating current user profile: {e}")
            return JsonResponse({'error': 'Error accessing your profile'}, status=500)
            
        try:
            target_profile, created = UserProfile.objects.get_or_create(user=target_user)
            if created:
                print(f"Created new profile for {target_user.username}")
        except Exception as e:
            print(f"Error creating target user profile: {e}")
            return JsonResponse({'error': 'Error accessing target profile'}, status=500)
        
        # Toggle follow status
        try:
            is_following = current_profile.toggle_follow(target_profile)
            print(f"Toggle follow result: {is_following}")
        except Exception as e:
            print(f"Error in toggle_follow: {e}")
            return JsonResponse({'error': 'Error updating follow status'}, status=500)
        
        return JsonResponse({
            'success': True,
            'is_following': is_following,
            'followers_count': target_profile.followers.count(),
            'following_count': current_profile.following.count(),
            'message': f'You are now {"following" if is_following else "not following"} {target_user.username}'
        })
        
    except Exception as e:
        print(f"Unexpected error in toggle_follow: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def followers_list(request, username):
    """Display list of followers for a user"""
    user = get_object_or_404(User, username=username)
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    followers = profile.followers.all().select_related('user')
    
    # Add follow status for current user
    current_user_profile = None
    if request.user.is_authenticated:
        current_user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Create a list with follow status
    followers_with_status = []
    for follower in followers:
        is_following = False
        if current_user_profile and current_user_profile != follower:
            is_following = current_user_profile.is_following(follower)
        followers_with_status.append({
            'profile': follower,
            'is_following': is_following
        })
    
    context = {
        'profile_user': user,
        'followers': followers_with_status,
        'is_followers_page': True,
    }
    return render(request, 'followers_following.html', context)

@login_required
def following_list(request, username):
    """Display list of users that this user is following"""
    user = get_object_or_404(User, username=username)
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    following = profile.following.all().select_related('user')
    
    # Add follow status for current user (all following users should show "Unfollow")
    current_user_profile = None
    if request.user.is_authenticated:
        current_user_profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Create a list with follow status
    following_with_status = []
    for following_profile in following:
        is_following = False
        if current_user_profile and current_user_profile != following_profile:
            is_following = current_user_profile.is_following(following_profile)
        following_with_status.append({
            'profile': following_profile,
            'is_following': is_following
        })
    
    context = {
        'profile_user': user,
        'following': following_with_status,
        'is_following_page': True,
    }
    return render(request, 'followers_following.html', context)